import json
import re
from datetime import datetime, timedelta

import redis
import requests

from config import Config
from . import celery
from .models import db, Submission, ContestSubmission, Problem, Contest

BASE_URL = None

redis_con = redis.StrictRedis.from_url(Config.DEFAULT_REDIS_URL)


@celery.task(bind=True)
def submit_problem(self, sid, in_contest=False):
    if in_contest:
        submission = ContestSubmission.query.get(int(sid))
    else:
        submission = Submission.query.get(int(sid))
    url = f"{BASE_URL}/submissions/"
    s = requests.session()
    data = {
        "oj_name": submission.oj_name,
        "problem_id": submission.problem_id,
        "language": submission.language,
        "source_code": submission.source_code,
    }
    try:
        r = s.post(url, data, timeout=10)
    except requests.exceptions.RequestException as exc:
        if self.request.retries == self.max_retries:
            submission.verdict = "Submit Failed"
            db.session.commit()
        raise self.retry(exc=exc, countdown=5)
    data = r.json()
    if data.get("status") != "success":
        submission.verdict = "Submit Failed"
        return
    submission.run_id = data.get("id")
    db.session.commit()
    refresh_submit_status.delay(sid, in_contest)


@celery.task(bind=True, default_retry_delay=1)
def refresh_submit_status(self, sid, in_contest=False):
    if in_contest:
        submission = ContestSubmission.query.get(int(sid))
    else:
        submission = Submission.query.get(int(sid))
    url = f"{BASE_URL}/submissions/{submission.run_id}"
    s = requests.session()
    try:
        r = s.get(url, timeout=5)
    except requests.exceptions.RequestException as exc:
        raise self.retry(max_retries=120, exc=exc, countdown=self.request.retries + 1)
    data = r.json()
    if "error" in data:
        self.retry()
    verdict = data.get("verdict", "Queuing")
    exe_time = data.get("exe_time", None)
    exe_mem = data.get("exe_mem", None)
    if verdict and verdict != submission.verdict:
        submission.verdict = verdict
        submission.exe_time = exe_time or 0
        submission.exe_mem = exe_mem or 0
        db.session.commit()
    if verdict in ("Queuing", "Being Judged"):
        raise self.retry(max_retries=120, countdown=self.request.retries + 1)
    if not in_contest:
        user = submission.user
        user.submitted += 1
        kvs = {
            "user_id": submission.user_id,
            "oj_name": submission.oj_name,
            "problem_id": submission.problem_id,
            "verdict": submission.verdict,
        }
        if Submission.query.filter_by(**kvs).count() == 1 and verdict == "Accepted":
            problem = submission.problem
            problem.solved += 1
            user = submission.user
            user.solved += 1
    db.session.commit()


@celery.task(bind=True)
def refresh_problem(self, oj_name, problem_id):
    url = f"{BASE_URL}/problems/{oj_name}/{problem_id}"
    s = requests.session()
    try:
        r = s.post(url, timeout=5)
    except requests.exceptions.RequestException as exc:
        raise self.retry(exc=exc, countdown=5)
    data = r.json()
    if data.get("status") == "success":
        update_problem.delay(oj_name=oj_name, problem_id=problem_id)


@celery.task(bind=True, max_retries=10, default_retry_delay=5)
def update_problem(self, oj_name, problem_id):
    url = f"{BASE_URL}/problems/{oj_name}/{problem_id}"
    s = requests.session()
    try:
        r = s.get(url, timeout=5)
    except requests.exceptions.RequestException as exc:
        raise self.retry(exc=exc)
    if "error" in r.json():
        raise self.retry()
    last_update = datetime.utcfromtimestamp(r.json()["last_update"])
    problem = Problem.query.filter_by(oj_name=oj_name, problem_id=problem_id).first()
    if problem and last_update - problem.last_update < timedelta(minutes=10):
        self.retry()
    if problem is None:
        problem = Problem()
    problem.last_update = last_update
    for attr in r.json():
        if attr != "last_update" and hasattr(problem, attr):
            value = r.json()[attr]
            if value:
                setattr(problem, attr, value)
    db.session.add(problem)
    db.session.commit()


@celery.task(bind=True, name="refresh_contest_info")
def refresh_contest_info(self, contest_id):
    contest = Contest.query.get(int(contest_id))
    if not contest or not contest.is_clone:
        return
    res = re.match(r"^(.*?)_ct_([0-9]+)$", contest.clone_name)
    if not res:
        return
    last = redis_con.get(f"vjudge-last-refresh-contest-{contest_id}") or 0
    last = datetime.fromtimestamp(float(last))
    if (
        datetime.now() - last
        < timedelta(hours=1)
        < contest.start_time - datetime.utcnow()
    ):
        return
    site, cid = res.groups()
    url = f"{BASE_URL}/contests/{site}/{cid}"
    s = requests.session()
    try:
        s.post(url, timeout=10)
        r = s.get(url, timeout=10)
    except requests.exceptions.RequestException as exc:
        raise self.retry(exc=exc, countdown=30)
    if "error" in r.json():
        raise self.retry(countdown=30)
    contest_data = r.json()["contest"]
    problems = r.json()["problems"]
    contest.title = contest_data.get("title", "")
    contest.public = contest_data.get("public", False)
    contest.status = contest_data.get("status", "Pending")
    start_time = contest_data.get("start_time", 0)
    end_time = contest_data.get("end_time", 0)
    contest.start_time = datetime.utcfromtimestamp(start_time)
    contest.end_time = datetime.utcfromtimestamp(end_time)
    problem_list = []
    for p in problems:
        oj_name = p["oj_name"]
        problem_id = p["problem_id"]
        problem = (
            Problem.query.filter_by(oj_name=oj_name, problem_id=problem_id).first()
            or Problem()
        )
        for attr in p:
            if attr == "last_update":
                problem.last_update = datetime.utcfromtimestamp(p[attr])
            elif hasattr(problem, attr):
                value = p[attr]
                if value:
                    setattr(problem, attr, value)
        db.session.add(problem)
        problem_list.append((problem.problem_id, problem.oj_name, problem.problem_id))
        contest.problems = json.dumps(problem_list)
    db.session.add(contest)
    db.session.commit()
    redis_con.set(
        f"vjudge-last-refresh-contest-{contest_id}",
        datetime.now().timestamp(),
        ex=60 * 60,
    )
    if contest.problems == "[]" and contest.start_time - datetime.utcnow() < timedelta(
        minutes=5
    ):
        raise self.retry(max_retries=10, countdown=30)


def update_recent_contest(self):
    url = f"{BASE_URL}/contests/hdu"
    s = requests.session()
    try:
        r = s.get(url, timeout=10)
    except requests.exceptions.RequestException as exc:
        raise self.retry(exc=exc, countdown=5)
    contests = r.json()["contests"]
    contests.reverse()
    for contest in contests:
        contest_id = contest.get("contest_id")
        if contest_id is None:
            continue
        title = contest.get("title", "")
        status = contest.get("status", "Pending")
        public = contest.get("public", False)
        site = contest.get("site", "")
        start_time = contest.get("start_time", 0)
        end_time = contest.get("end_time", 0)
        oj_name = f"{site}_ct_{contest_id}"
        contest = Contest.query.filter_by(is_clone=True, clone_name=oj_name).first()
        if contest is None:
            contest = Contest()
            contest.is_clone = True
            contest.clone_name = oj_name
            contest.title = title
            contest.public = public
            contest.status = status
            contest.start_time = datetime.utcfromtimestamp(start_time)
            contest.end_time = datetime.utcfromtimestamp(end_time)
            db.session.add(contest)
        else:
            contest.clone_name = oj_name
            contest.title = title
            contest.public = public
            contest.status = status
        db.session.commit()


@celery.task(bind=True, name="refresh_recent_contest")
def refresh_recent_contest(self):
    last = redis_con.get("vjudge-last-refresh-recent-contest") or 0
    last = datetime.fromtimestamp(float(last))
    if datetime.now() - last >= timedelta(hours=12):
        update_recent_contest(self)
        redis_con.set("vjudge-last-refresh-recent-contest", datetime.now().timestamp())
    contests = Contest.query.all()
    for contest in contests:
        if contest.status != "Ended" and contest.start_time - timedelta(
            hours=6
        ) <= datetime.utcnow() <= contest.start_time + timedelta(hours=6):
            refresh_contest_info.delay(contest.id)


@celery.task(name="update_problem_all")
def update_problem_all():
    s = requests.session()
    url = f"{BASE_URL}/problems/"
    while url:
        try:
            r = s.get(url, timeout=5)
        except requests.exceptions.RequestException:
            return
        url = r.json()["next"]
        problem_list = r.json()["problems"]
        for p in problem_list:
            oj_name = p["oj_name"]
            problem_id = p["problem_id"]
            problem = Problem.query.filter_by(
                oj_name=oj_name, problem_id=problem_id
            ).first()
            if problem and datetime.utcnow() - problem.last_update < timedelta(
                hours=12
            ):
                continue
            if problem is None:
                problem = Problem()
            try:
                r = s.get(f"{BASE_URL}/problems/{oj_name}/{problem_id}", timeout=5)
            except requests.exceptions.RequestException:
                return
            for attr in r.json():
                if attr == "last_update":
                    problem.last_update = datetime.utcfromtimestamp(r.json()[attr])
                elif hasattr(problem, attr):
                    value = r.json()[attr]
                    if value:
                        setattr(problem, attr, value)
            db.session.add(problem)
            db.session.commit()
