import requests
from .models import db, Submission, Problem
from . import celery
from config import Config

from datetime import datetime, timedelta

base_url = Config.VJUDGE_REMOTE_URL


@celery.task()
def submit_problem(id):
    submission = Submission.query.get(int(id))
    url = base_url + '/problems/'
    s = requests.session()
    data = {
        'oj_name': submission.oj_name,
        'problem_id': submission.problem_id,
        'language': submission.language,
        'source_code': submission.source_code
    }
    r = s.post(url, data)
    if 'id' in r.json():
        submission.run_id = r.json()['id']
        refresh_submit_status.delay(id)
    else:
        submission.verdict = 'Submit Failed'
    db.session.commit()


@celery.task(bind=True)
def refresh_submit_status(self, id):
    submission = Submission.query.get(int(id))
    url = base_url + '/submissions/{}'.format(submission.run_id)
    s = requests.session()
    try:
        r = s.get(url, timeout=5)
    except requests.exceptions.RequestException as exc:
        raise self.retry(exc=exc, countdown=5)
    verdict = r.json().get('verdict', 'Queuing')
    exe_time = r.json().get('exe_time', 0)
    exe_mem = r.json().get('exe_mem', 0)
    if verdict and verdict != submission.verdict:
        submission.verdict = verdict
        submission.exe_time = exe_time
        submission.exe_mem = exe_mem
        db.session.commit()
    if verdict in ('Queuing', 'Being Judged'):
        raise self.retry(max_retries=300, countdown=1)


@celery.task(bind=True)
def refresh_problem(self, oj_name, problem_id):
    url = base_url + '/problems/{}/{}'.format(oj_name, problem_id)
    s = requests.session()
    try:
        s.post(url, timeout=5)
        update_problem.delay(oj_name=oj_name, problem_id=problem_id)
    except requests.exceptions.RequestException as exc:
        raise self.retry(exc=exc, countdown=5)


@celery.task(bind=True, max_retries=10, default_retry_delay=5)
def update_problem(self, oj_name, problem_id):
    url = base_url + '/problems/{}/{}'.format(oj_name, problem_id)
    s = requests.session()
    try:
        r = s.get(url, timeout=5)
    except requests.exceptions.RequestException as exc:
        raise self.retry(exc=exc)
    if 'error' in r.json():
        raise self.retry()
    last_update = datetime.fromtimestamp(r.json()['last_update'])
    problem = Problem.query.filter_by(oj_name=oj_name, problem_id=problem_id).first()
    if problem and last_update - problem.last_update < timedelta(minutes=1):
        self.retry()
    if problem is None:
        problem = Problem()
    for attr in r.json():
        if attr != 'last_update' and hasattr(problem, attr):
            setattr(problem, attr, r.json()[attr])
    db.session.add(problem)
    db.session.commit()
