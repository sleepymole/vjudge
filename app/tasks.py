import requests
from sqlalchemy import or_
from .models import db, Submission, ContestSubmission, Problem
from . import celery
from config import Config

from datetime import datetime, timedelta

BASE_URL = Config.VJUDGE_REMOTE_URL


@celery.task(bind=True)
def submit_problem(self, sid, in_contest=False):
    if in_contest:
        submission = ContestSubmission.query.get(int(sid))
    else:
        submission = Submission.query.get(int(sid))
    url = f'{BASE_URL}/submissions/'
    s = requests.session()
    data = {
        'oj_name': submission.oj_name,
        'problem_id': submission.problem_id,
        'language': submission.language,
        'source_code': submission.source_code
    }
    try:
        r = s.post(url, data)
    except requests.exceptions.RequestException as exc:
        if self.request.retries == self.max_retries:
            submission.verdict = 'Submit Failed'
            db.session.commit()
        raise self.retry(exc=exc, countdown=5)
    data = r.json()
    if data.get('status') != 'success':
        submission.verdict = 'Submit Failed'
    submission.run_id = data.get('id')
    refresh_submit_status.delay(sid)
    db.session.commit()


@celery.task(bind=True, default_retry_delay=1)
def refresh_submit_status(self, sid, in_contest=False):
    if in_contest:
        submission = ContestSubmission.query.get(int(sid))
    else:
        submission = Submission.query.get(int(sid))
    url = f'{BASE_URL}/submissions/{submission.run_id}'
    s = requests.session()
    try:
        r = s.get(url, timeout=5)
    except requests.exceptions.RequestException as exc:
        raise self.retry(exc=exc, countdown=5)
    data = r.json()
    if 'error' in data:
        self.retry()
    verdict = data.get('verdict', 'Queuing')
    exe_time = data.get('exe_time', None)
    exe_mem = data.get('exe_mem', None)
    if verdict and verdict != submission.verdict:
        submission.verdict = verdict
        submission.exe_time = exe_time or 0
        submission.exe_mem = exe_mem or 0
        db.session.commit()
    if verdict in ('Queuing', 'Being Judged'):
        raise self.retry(max_retries=120, countdown=self.request.retries + 1)
    if not in_contest:
        user = submission.user
        user.submitted += 1
        kvs = {'user_id': submission.user_id, 'oj_name': submission.oj_name,
               'problem_id': submission.problem_id, 'verdict': submission.verdict}
        if Submission.query.filter_by(**kvs).count() == 1 and verdict == 'Accepted':
            problem = submission.problem
            problem.solved += 1
            user = submission.user
            user.solved += 1
    db.session.commit()


@celery.task(bind=True)
def refresh_problem(self, oj_name, problem_id):
    url = f'{BASE_URL}/problems/{oj_name}/{problem_id}'
    s = requests.session()
    try:
        r = s.post(url, timeout=5)
    except requests.exceptions.RequestException as exc:
        raise self.retry(exc=exc, countdown=5)
    data = r.json()
    if data.get('status') == 'success':
        update_problem.delay(oj_name=oj_name, problem_id=problem_id)


@celery.task(bind=True, max_retries=10, default_retry_delay=5)
def update_problem(self, oj_name, problem_id):
    url = f'{BASE_URL}/problems/{oj_name}/{problem_id}'
    s = requests.session()
    try:
        r = s.get(url, timeout=5)
    except requests.exceptions.RequestException as exc:
        raise self.retry(exc=exc)
    if 'error' in r.json():
        raise self.retry()
    last_update = datetime.fromtimestamp(r.json()['last_update'])
    problem = Problem.query.filter_by(oj_name=oj_name, problem_id=problem_id).first()
    if problem and last_update - problem.last_update < timedelta(minutes=10):
        self.retry()
    if problem is None:
        problem = Problem()
    problem.last_update = last_update
    for attr in r.json():
        if attr != 'last_update' and hasattr(problem, attr):
            value = r.json()[attr]
            if value:
                setattr(problem, attr, value)
    db.session.add(problem)
    db.session.commit()


@celery.task(name='scan_unfinished_submission')
def scan_unfinished_submission():
    submissions = Submission.query.filter(
        or_(Submission.verdict == 'Queuing', Submission.verdict == 'Being Judged')).all()
    for submission in submissions:
        if submission.run_id:
            refresh_submit_status.delay(submission.id)
        else:
            submit_problem.delay(submission.id)
    contest_submissions = ContestSubmission.query.filter(
        or_(ContestSubmission.verdict == 'Queuing', ContestSubmission.verdict == 'Being Judged')).all()
    for submission in contest_submissions:
        if submission.run_id:
            refresh_submit_status.delay(submission.id, True)
        else:
            submit_problem.delay(submission.id, True)


@celery.task(name='update_problem_all')
def update_problem_all():
    s = requests.session()
    url = f'{BASE_URL}/problems/'
    while url:
        try:
            r = s.get(url)
        except requests.exceptions.RequestException:
            return
        url = r.json()['next']
        problem_list = r.json()['problems']
        for p in problem_list:
            oj_name = p['oj_name']
            problem_id = p['problem_id']
            problem = Problem.query.filter_by(oj_name=oj_name, problem_id=problem_id).first()
            if problem and datetime.utcnow() - problem.last_update < timedelta(hours=12):
                continue
            if problem is None:
                problem = Problem()
            try:
                r = s.get(f'{BASE_URL}/problems/{oj_name}/{problem_id}')
            except requests.exceptions.RequestException:
                return
            for attr in r.json():
                if attr == 'last_update':
                    problem.last_update = datetime.fromtimestamp(r.json()[attr])
                elif hasattr(problem, attr):
                    value = r.json()[attr]
                    if value:
                        setattr(problem, attr, value)
            db.session.add(problem)
            db.session.commit()
