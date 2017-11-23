import requests
import threading
from queue import Queue
from abc import ABCMeta, abstractclassmethod
from config import OJ_ACCOUNTS, get_header
from server.models import Submission
from server import db
from . import exceptions


class BaseClient(metaclass=ABCMeta):
    def __init__(self):
        self._session = requests.session()
        self._session.headers.update(get_header())

    @abstractclassmethod
    def login(self, username, password):
        pass

    @abstractclassmethod
    def check_login(self):
        pass

    @abstractclassmethod
    def update_cookies(self):
        pass

    @abstractclassmethod
    def get_problem(self, problem_id):
        pass

    @abstractclassmethod
    def submit_problem(self, problem_id, language, source_code):
        pass

    @abstractclassmethod
    def get_submit_status(self, run_id, **kwargs):
        pass


class VJudge(threading.Thread):
    def __init__(self, queue):
        threading.Thread.__init__(self)
        self.queue = queue
        self.judge_queues = {}
        self.status_queues = {}
        self.available_ojs = []

    def run(self):
        for oj_name in OJ_ACCOUNTS:
            self.judge_queues[oj_name] = Queue()
            self.status_queues[oj_name] = Queue()
            accounts = OJ_ACCOUNTS[oj_name]
            available = False
            for username in accounts:
                password = accounts[username]
                client = self._get_oj_client(oj_name, auth=(username, password))
                if client is not None:
                    available = True
                    threading.Thread(target=self.judge, args=(client, oj_name, username), daemon=True).start()
            if available:
                self.available_ojs.append(oj_name)
                threading.Thread(target=self.refresh_status, args=(oj_name,), daemon=True).start()
        threading.Thread(target=self.handle_requests, daemon=True).start()
        self.refresh_status_all()

    def judge(self, client, oj_name, remote_user_id):
        queue = self.judge_queues[oj_name]
        while True:
            run_id = queue.get()
            submission = db.session.query(Submission).filter_by(run_id=run_id).one()
            try:
                remote_run_id = client.submit_problem(submission.problem_id, submission.language,
                                                      submission.source_code)
            except (exceptions.SubmitError, exceptions.ConnectionError):
                submission.verdict = 'Submit Failed'
                db.session.commit()
            except exceptions.LoginExpired:
                try:
                    client.update_cookies()
                    queue.put(run_id)
                except exceptions.ConnectionError:
                    submission.verdict = 'Submit Failed'
                    db.session.commit()
            else:
                submission.update(remote_run_id=remote_run_id, verdict='Being Judged', remote_user_id=remote_user_id)
                db.session.commit()
                self.status_queues[oj_name].put(run_id)

    def refresh_status(self, oj_name):
        queue = self.status_queues[oj_name]
        client = self._get_oj_client(oj_name)
        while True:
            run_id = queue.get()
            submission = db.session.query(Submission).filter_by(run_id=run_id).one()
            try:
                verdict, exe_time, exe_mem = client.get_submit_status(submission.remote_run_id,
                                                                      user_id=submission.remote_user_id,
                                                                      problem_id=submission.problem_id)
                if verdict in ('Being Judged', 'Queuing', 'Compiling', 'Running'):
                    queue.put(run_id)
                else:
                    submission.update(verdict=verdict, exe_time=exe_time, exe_mem=exe_mem)
                    db.session.commit()
            except exceptions.ConnectionError:
                pass

    def refresh_status_all(self):
        submissions = db.session.query(Submission).filter(Submission.verdict == 'Being Judged').filter(
            Submission.remote_run_id.isnot(None)).all()
        for submission in submissions:
            if submission.oj_name in self.available_ojs:
                self.status_queues[submission.oj_name].put(submission.run_id)

    def handle_requests(self):
        while True:
            run_id = self.queue.get()
            submission = db.session.query(Submission).filter_by(run_id=run_id).one()
            if submission.oj_name not in self.available_ojs:
                submission.verdict = 'Submit Failed'
                db.session.commit()
                continue
            self.judge_queues[submission.oj_name].put(run_id)

    @staticmethod
    def _get_oj_client(oj_name, auth=None):
        import importlib
        try:
            oj = importlib.import_module('.' + oj_name, __package__)
        except ModuleNotFoundError:
            return
        try:
            client = oj.Client()
            if auth is not None:
                client.login(*auth)
            return client
        except (exceptions.LoginError, exceptions.ConnectionError):
            pass
