import asyncio
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from queue import Queue, Empty

import redis
from sqlalchemy import or_

from config import REDIS_CONFIG, logger
from .models import db, Submission, Problem, Contest
from .site import get_client_by_oj_name, exceptions


class StatusCrawler(threading.Thread):
    def __init__(self, client, daemon=None):
        super().__init__(daemon=daemon)
        self._client = client
        self._user_id = client.get_user_id()
        self._name = client.get_name()
        self._start_event = threading.Event()
        self._stop_event = threading.Event()
        self._tasks = []
        self._thread = None
        self._loop = None

    def run(self):
        self._thread = threading.current_thread()
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.call_soon(self._start_event.set)
        self._loop.run_forever()
        pending_tasks = self._pending_tasks()
        self._loop.run_until_complete(asyncio.gather(*pending_tasks))

    def wait_start(self, timeout=None):
        return self._start_event.wait(timeout)

    def add_task(self, submission_id):
        if not self._start_event.is_set():
            raise RuntimeError('Cannot add task before crawler is started')
        if self._stop_event.is_set():
            raise RuntimeError('Cannot add task when crawler is stopping')
        self._loop.call_soon_threadsafe(
            asyncio.ensure_future, self._crawl_status(submission_id))
        return True

    def stop(self):
        if not self._start_event.is_set():
            raise RuntimeError('Cannot stop crawler before it is started')
        if self._stop_event.is_set():
            raise RuntimeError('Crawler can only be stopped once')
        self._stop_event.set()
        self._loop.call_soon_threadsafe(self._loop.stop)

    async def _crawl_status(self, submission_id):
        submission = Submission.query.get(submission_id)
        if (not submission.run_id or submission.oj_name != self._name
                or submission.verdict != 'Being Judged'):
            return
        for delay in range(120):
            await asyncio.sleep(delay)
            try:
                verdict, exe_time, exe_mem = self._client.get_submit_status(
                    submission.run_id,
                    user_id=submission.user_id,
                    problem_id=submission.problem_id)
            except exceptions.ConnectionError as e:
                submission.verdict = 'Judge Failed'
                db.session.commit()
                logger.error(f'Crawled status failed, submission_id: {submission.id}, reason: {e}')
                return
            except exceptions.LoginRequired:
                try:
                    self._client.update_cookies()
                    logger.debug(
                        f'StatusCrawler login expired, login again, name: {self._name}, user_id: {self._user_id}')
                    continue
                except exceptions.ConnectionError as e:
                    submission.verdict = 'Judge Failed'
                    db.session.commit()
                    logger.error(f'Crawled status failed, submission_id: {submission.id}, reason: {e}')
                    return
            if verdict not in ('Being Judged', 'Queuing', 'Compiling', 'Running'):
                submission.verdict = verdict
                submission.exe_time = exe_time
                submission.exe_mem = exe_mem
                db.session.commit()
                logger.info(
                    f'Crawled status successfully, submission_id: {submission.id}, verdict: {submission.verdict}')
                return
        submission.verdict = 'Judge Failed'
        db.session.commit()
        logger.error(f'Crawled status failed, submission_id: {submission.id}, reason: Timeout')

    def _pending_tasks(self):
        if hasattr(asyncio, 'all_tasks'):
            pending_tasks = asyncio.all_tasks(self._loop)
        else:
            pending_tasks = {t for t in asyncio.Task.all_tasks(self._loop) if not t.done()}
        return pending_tasks

    def __repr__(self):
        return f'<StatusCrawler(oj_name={self._name}, user_id={self._user_id})>'


class Submitter(threading.Thread):
    def __init__(self, client, submit_queue, status_crawler, daemon=None):
        super().__init__(daemon=daemon)
        self._client = client
        self._user_id = client.get_user_id()
        self._name = client.get_name()
        self._submit_queue = submit_queue
        self._status_crawler = status_crawler
        self._stop_event = threading.Event()

    def run(self):
        self._status_crawler.start()
        self._status_crawler.wait_start()
        logger.info(f'Started submitter, name: {self._name}, user_id: {self._user_id}')
        while True:
            try:
                submission = Submission.query.get(self._submit_queue.get(timeout=60))
            except Empty:
                if self._stop_event.is_set():
                    break
                continue
            logger.info(f'Start judging submission {submission.id}, verdict: {submission.verdict}')
            if submission.verdict not in ('Queuing', 'Being Judged'):
                continue
            if submission.verdict == 'Being Judged':
                self._status_crawler.add_task(submission.id)
                continue
            try:
                run_id = self._client.submit_problem(
                    submission.problem_id, submission.language, submission.source_code)
            except (exceptions.SubmitError, exceptions.ConnectionError) as e:
                submission.verdict = 'Submit Failed'
                db.session.commit()
                logger.error(f'Submission {submission.id} is submitted failed, reason: {e}')
            except exceptions.LoginRequired:
                try:
                    self._client.update_cookies()
                    self._submit_queue.put(submission.id)
                    logger.debug(
                        f'Submitter login is expired, login again, name: {self._name}, user_id: {self._user_id}')
                except exceptions.ConnectionError as e:
                    submission.verdict = 'Submit Failed'
                    db.session.commit()
                    logger.error(f'Submission {submission.id} is submitted failed, reason: {e}')
            else:
                submission.run_id = run_id
                submission.user_id = self._user_id
                submission.verdict = 'Being Judged'
                db.session.commit()
                logger.info(f'Submission {submission.id} is submitted successfully')
                self._status_crawler.add_task(submission.id)
            time.sleep(5)
        logger.info(f'Stopping submitter, name: {self._name}, user_id: {self._user_id}')
        self._status_crawler.stop()
        self._status_crawler.join()
        logger.info(f'Stopped submitter, name: {self._name}, user_id: {self._user_id}')

    def stop(self):
        self._stop_event.set()

    def __repr__(self):
        return f'<Submitter(oj_name={self._name}, user_id={self._user_id})>'


class PageCrawler(threading.Thread):
    def __init__(self, client, page_queue, daemon=None):
        super().__init__(daemon=daemon)
        self._client = client
        self._name = client.get_name()
        self._user_id = client.get_user_id()
        self._client_type = client.get_client_type()
        self._supported_crawl_type = ['problem']
        if self._client_type == 'contest':
            self._supported_crawl_type.append('contest')
        self._page_queue = page_queue
        self._stop_event = threading.Event()

    def run(self):
        logger.info(f'Started PageCrawler, name: {self._name}, user_id: {self._user_id}')
        while True:
            try:
                data = self._page_queue.get(timeout=60)
            except Empty:
                if self._stop_event.is_set():
                    break
                continue
            if not isinstance(data, dict):
                logger.error(f'PageCrawler: data type should be dict, data: "{data}"')
                continue
            crawl_type = data.get('type')
            if crawl_type not in self._supported_crawl_type:
                logger.error(f'Unsupported crawl_type: {crawl_type}')
                continue
            try:
                if crawl_type == 'problem':
                    problem_id = data.get('problem_id')
                    if problem_id:
                        self._crawl_problem(problem_id)
                    else:
                        self._crawl_problem_all()
                elif crawl_type == 'contest':
                    self._crawl_contest()
            except exceptions.ConnectionError as e:
                logger.error(f'Crawled page failed, name: {self._name}, user_id: {self._user_id}, reason: {e}')
            except exceptions.LoginRequired:
                try:
                    self._client.update_cookies()
                    self._page_queue.put(data)
                    logger.debug(
                        f'PageCrawler login expired, login again, name: {self._name}, user_id: {self._user_id}')
                except exceptions.ConnectionError as e:
                    logger.error(f'Crawled contest failed, name: {self._name}, user_id: {self._user_id}, reason: {e}')
        logger.info(f'Stopped PageCrawler, name: {self._name}, user_id: {self._user_id}')

    def stop(self):
        self._stop_event.set()

    def _crawl_problem(self, problem_id):
        result = self._client.get_problem(problem_id)
        if not isinstance(result, dict):
            logger.error(f'No such problem, name: {self._name}, '
                         f'user_id: {self._user_id}, problem_id: {problem_id}')
            return
        problem = Problem.query.filter_by(oj_name=self._name, problem_id=problem_id).first() or Problem()
        problem.oj_name = self._name
        problem.problem_id = problem_id
        problem.last_update = datetime.utcnow()
        problem.title = result.get('title')
        problem.description = result.get('description')
        problem.input = result.get('input')
        problem.output = result.get('output')
        problem.sample_input = result.get('sample_input')
        problem.sample_output = result.get('sample_output')
        problem.time_limit = result.get('time_limit')
        problem.mem_limit = result.get('mem_limit')
        db.session.add(problem)
        db.session.commit()
        logger.info(f'Crawled problem successfully, name: {self._name}, '
                    f'user_id: {self._user_id}, problem_id: {problem_id}')

    def _crawl_problem_all(self):
        problem_list = self._client.get_problem_list()
        for problem_id in problem_list:
            self._crawl_problem(problem_id)

    def _crawl_contest(self):
        contest = Contest.query.filter_by(oj_name=self._name).first() or Contest()
        self._client.refresh_contest_info()
        contest_info = self._client.get_contest_info()
        contest.oj_name = self._name
        contest.site = contest_info.site
        contest.contest_id = contest_info.contest_id
        contest.title = contest_info.title
        contest.public = contest_info.public
        contest.status = contest_info.status
        contest.start_time = datetime.fromtimestamp(contest_info.start_time, tz=timezone.utc)
        contest.end_time = datetime.fromtimestamp(contest_info.end_time, tz=timezone.utc)
        db.session.add(contest)
        db.session.commit()
        logger.info(f'Crawled contest successfully, name: {self._name}, '
                    f'user_id: {self._user_id}, contest_id: {contest.contest_id}')
        self._crawl_problem_all()


class SubmitterHandler(threading.Thread):
    def __init__(self, normal_accounts, contest_accounts, daemon=None):
        super().__init__(daemon=daemon)
        self._redis_key = REDIS_CONFIG['queue']['submitter_queue']
        self._redis_con = redis.StrictRedis(
            host=REDIS_CONFIG['host'], port=REDIS_CONFIG['port'], db=REDIS_CONFIG['db'])
        self._normal_accounts = normal_accounts
        self._contest_accounts = contest_accounts
        self._running_submitters = {}
        self._stopping_submitters = set()
        self._queues = {}

    def run(self):
        self._scan_unfinished_tasks()
        last_clean = datetime.utcnow()
        while True:
            data = self._redis_con.brpop(self._redis_key, timeout=600)
            if datetime.utcnow() - last_clean > timedelta(hours=1):
                self._clean_free_submitters()
                last_clean = datetime.utcnow()
            if not data:
                continue
            try:
                submission_id = int(data[1])
            except (ValueError, TypeError):
                logger.error(f'SubmitterHandler: receive corrupt data "{data[1]}"')
                continue
            submission = Submission.query.get(submission_id)
            if not submission:
                logger.error(f'Submission {submission_id} is not found')
                continue
            if submission.oj_name not in self._normal_accounts and submission.oj_name not in self._contest_accounts:
                logger.error(f'Unsupported oj_name: {submission.oj_name}')
                continue
            if submission.oj_name not in self._queues:
                self._queues[submission.oj_name] = Queue()
            submit_queue = self._queues.get(submission.oj_name)
            if submission.oj_name not in self._running_submitters:
                if not self._start_new_submitters(submission.oj_name, submit_queue):
                    submission.verdict = 'Submit Failed'
                    db.session.commit()
                    logger.error(f'Cannot start client for {submission.oj_name}')
                    continue
            assert submission.oj_name in self._running_submitters
            submit_queue.put(submission.id)

    def _scan_unfinished_tasks(self):
        submissions = Submission.query.filter(
            or_(Submission.verdict == 'Queuing', Submission.verdict == 'Being Judged'))
        for submission in submissions:
            self._redis_con.lpush(self._redis_key, submission.id)

    def _start_new_submitters(self, oj_name, submit_queue):
        submitter_info = {'submitters': {}}
        submitters = submitter_info.get('submitters')
        accounts = {}
        if oj_name in self._normal_accounts:
            accounts = self._normal_accounts[oj_name]
        if oj_name in self._contest_accounts:
            accounts = self._contest_accounts[oj_name]
        for auth in accounts:
            try:
                crawler = StatusCrawler(get_client_by_oj_name(oj_name, auth), daemon=True)
                submitter = Submitter(get_client_by_oj_name(oj_name, auth), submit_queue, crawler, daemon=True)
            except exceptions.JudgeException as e:
                logger.error(f'Create submitter failed, name: {oj_name}, user_id: auth[0], reason: {e}')
                continue
            submitter.start()
            submitters[auth[0]] = submitter
        if not submitters:
            return False
        submitter_info['start_time'] = datetime.utcnow()
        self._running_submitters[oj_name] = submitter_info
        return True

    def _clean_free_submitters(self):
        free_clients = []
        for oj_name in self._running_submitters:
            submitter_info = self._running_submitters[oj_name]
            if datetime.utcnow() - submitter_info['start_time'] > timedelta(hours=1):
                free_clients.append(oj_name)
        for oj_name in free_clients:
            submitter_info = self._running_submitters[oj_name]
            submitters = submitter_info.get('submitters')
            for user_id in submitters:
                submitter = submitters.get(user_id)
                submitter.stop()
                self._stopping_submitters.add(submitter)
            self._running_submitters.pop(oj_name)
            logger.info(f'No more task, stop all {oj_name} submitters')
        stopped_submitters = []
        for submitter in self._stopping_submitters:
            if not submitter.is_alive():
                stopped_submitters.append(submitter)
        for submitter in stopped_submitters:
            self._stopping_submitters.remove(submitter)
        logger.info('Cleaned free submitters')
        logger.info(f'Running submitters: {self._running_submitters}')
        logger.info(f'Stopping submitters: {self._stopping_submitters}')


class CrawlerHandler(threading.Thread):
    def __init__(self, normal_accounts, contest_accounts, daemon=None):
        super().__init__(daemon=daemon)
        self._redis_key = REDIS_CONFIG['queue']['crawler_queue']
        self._redis_con = redis.StrictRedis(
            host=REDIS_CONFIG['host'], port=REDIS_CONFIG['port'], db=REDIS_CONFIG['db'])
        self._normal_accounts = normal_accounts
        self._contest_accounts = contest_accounts
        self._running_crawlers = {}
        self._stopping_crawlers = set()
        self._queues = {}

    def run(self):
        last_clean = datetime.utcnow()
        while True:
            data = self._redis_con.brpop(self._redis_key, timeout=600)
            if datetime.utcnow() - last_clean > timedelta(hours=1):
                self._clean_free_crawlers()
                last_clean = datetime.utcnow()
            if not data:
                continue
            try:
                data = json.loads(data[1])
            except json.JSONDecodeError:
                logger.error(f'CrawlerHandler: received corrupt data "{data[1]}"')
                continue
            if not isinstance(data, dict):
                logger.error(f'CrawlerHandler: data type should be dict, data: "{data}"')
                continue
            crawl_type = data.get('type')
            oj_name = data.get('oj_name')
            if crawl_type not in ('problem', 'contest'):
                logger.error(f'Unsupported crawl_type: {crawl_type}')
                continue
            if oj_name not in self._normal_accounts and oj_name not in self._contest_accounts:
                logger.error(f'Unsupported oj_name: {oj_name}')
                continue
            if oj_name not in self._queues:
                self._queues[oj_name] = Queue()
            crawl_queue = self._queues.get(oj_name)
            if oj_name not in self._running_crawlers:
                if not self._start_new_crawlers(oj_name, crawl_queue):
                    logger.error(f'Cannot start client for {oj_name}')
                    continue
            assert oj_name in self._running_crawlers
            if crawl_type == 'problem':
                crawl_all = data.get('all')
                problem_id = data.get('problem_id')
                if crawl_all is not True:
                    crawl_all = False
                if not crawl_all and problem_id is None:
                    logger.error('Missing crawl_params: problem_id')
                    continue
                data = {'type': 'problem'}
                if not crawl_all:
                    data['problem_id'] = problem_id
                crawl_queue.put(data)
            elif crawl_type == 'contest':
                crawl_queue.put({'type': 'contest'})

    def _start_new_crawlers(self, oj_name, crawl_queue):
        crawler_info = {'crawlers': {}}
        crawlers = crawler_info.get('crawlers')
        accounts = {}
        if oj_name in self._normal_accounts:
            accounts = self._normal_accounts[oj_name]
        if oj_name in self._contest_accounts:
            accounts = self._contest_accounts[oj_name]
        for auth in accounts:
            try:
                crawler = PageCrawler(get_client_by_oj_name(oj_name, auth), crawl_queue, daemon=True)
            except exceptions.JudgeException as e:
                logger.error(f'Create crawler failed, name: {oj_name}, user_id: {auth[0]}, reason: {e}')
                continue
            crawler.start()
            crawlers[auth[0]] = crawler
        if not crawlers:
            return False
        crawler_info['start_time'] = datetime.utcnow()
        self._running_crawlers[oj_name] = crawler_info
        return True

    def _clean_free_crawlers(self):
        free_clients = []
        for oj_name in self._running_crawlers:
            crawler_info = self._running_crawlers[oj_name]
            if datetime.utcnow() - crawler_info['start_time'] > timedelta(hours=1):
                free_clients.append(oj_name)
        for oj_name in free_clients:
            crawler_info = self._running_crawlers[oj_name]
            crawlers = crawler_info.get('crawlers')
            for user_id in crawlers:
                crawler = crawlers.get(user_id)
                crawler.stop()
                self._stopping_crawlers.add(crawler)
            self._running_crawlers.pop(oj_name)
            logger.info(f'No more task, stop all {oj_name} crawlers')
        stopped_crawlers = []
        for crawler in self._stopping_crawlers:
            if not crawler.is_alive():
                stopped_crawlers.append(crawler)
        for crawler in stopped_crawlers:
            self._stopping_crawlers.remove(crawler)
        logger.info('Cleaned free crawlers')
        logger.info(f'Running crawlers: {self._running_crawlers}')
        logger.info(f'Stopping crawlers: {self._stopping_crawlers}')


class VJudge(object):
    def __init__(self, normal_accounts=None, contest_accounts=None):
        if not normal_accounts and not contest_accounts:
            logger.warning('Neither normal_accounts nor contest_accounts has available account, '
                           'submitter and crawler will not work')
        self._normal_accounts = normal_accounts or {}
        self._contest_accounts = contest_accounts or {}

    @property
    def normal_accounts(self):
        return self._normal_accounts

    @property
    def contest_accounts(self):
        return self._contest_accounts

    def start(self):
        submitter_handle = SubmitterHandler(self._normal_accounts, self._contest_accounts, True)
        crawler_handle = CrawlerHandler(self._normal_accounts, self._contest_accounts, True)
        submitter_handle.start()
        crawler_handle.start()
        submitter_handle.join()
        crawler_handle.join()
