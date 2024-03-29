import json
import re
from datetime import datetime, timedelta

import redis
from sqlalchemy import or_

from config import Config
from core import db as core_db
from core.models import Contest as CoreContest
from core.models import Problem as CoreProblem
from core.models import Submission as CoreSubmission
from core.site import contest_clients
from . import celery
from .models import db, Submission, ContestSubmission, Problem, Contest

redis_con = redis.StrictRedis.from_url(Config.DEFAULT_REDIS_URL)


@celery.task(bind=True)
def submit_problem(self, sid, in_contest=False):
    if in_contest:
        submission = ContestSubmission.query.get(int(sid))
    else:
        submission = Submission.query.get(int(sid))
    core_submission = CoreSubmission(
        oj_name=submission.oj_name,
        problem_id=submission.problem_id,
        language=submission.language,
        source_code=submission.source_code,
    )
    core_db.session.add(core_submission)
    core_db.session.commit()
    redis_con.lpush("vjudge-submitter-tasks", core_submission.id)
    submission.run_id = core_submission.id
    db.session.commit()
    refresh_submit_status.delay(sid, in_contest)


@celery.task(bind=True, default_retry_delay=1)
def refresh_submit_status(self, sid, in_contest=False):
    if in_contest:
        submission = ContestSubmission.query.get(int(sid))
    else:
        submission = Submission.query.get(int(sid))
    core_submission = CoreSubmission.query.get(submission.run_id)
    verdict = core_submission.verdict
    exe_time = core_submission.exe_time
    exe_mem = core_submission.exe_mem
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
    redis_con.lpush(
        "vjudge-crawler-tasks",
        json.dumps(
            {
                "oj_name": oj_name,
                "type": "problem",
                "all": False,
                "problem_id": problem_id,
            }
        ),
    )
    update_problem.delay(oj_name=oj_name, problem_id=problem_id)


@celery.task(bind=True, max_retries=10, default_retry_delay=5)
def update_problem(self, oj_name, problem_id):
    if not try_update_problem(oj_name, problem_id):
        raise self.retry()


def try_update_problem(oj_name, problem_id):
    core_problem = CoreProblem.query.filter_by(
        oj_name=oj_name, problem_id=problem_id
    ).first()
    if core_problem is None:
        return False
    problem = (
        Problem.query.filter_by(oj_name=oj_name, problem_id=problem_id).first()
        or Problem()
    )
    if problem.last_update == core_problem.last_update:
        return False

    problem.oj_name = core_problem.oj_name
    problem.problem_id = core_problem.problem_id
    problem.last_update = core_problem.last_update
    problem.title = core_problem.title
    problem.description = core_problem.description
    problem.input = core_problem.input
    problem.output = core_problem.output
    problem.sample_input = core_problem.sample_input
    problem.sample_output = core_problem.sample_output
    problem.time_limit = core_problem.time_limit
    problem.mem_limit = core_problem.mem_limit

    db.session.add(problem)
    db.session.commit()
    return True


@celery.task(bind=True, name="refresh_contest_info")
def refresh_contest_info(self, contest_id):
    contest = Contest.query.get(int(contest_id))
    if not contest or not contest.is_clone:
        return
    res = re.match(r"^(.*?)_ct_([0-9]+)$", contest.clone_name)
    if not res:
        return
    site, cid = res.groups()
    last = redis_con.get(f"vjudge-last-refresh-contest-{contest_id}") or 0
    last = datetime.fromtimestamp(float(last))
    if (
        datetime.now() - last
        < timedelta(hours=1)
        < contest.start_time - datetime.utcnow()
    ):
        return
    redis_con.lpush(
        "vjudge-crawler-tasks",
        json.dumps(
            {
                "oj_name": contest.clone_name,
                "type": "contest",
            }
        ),
    )

    core_contest = CoreContest.query.filter_by(site=site, contest_id=cid).first()
    if core_contest is None:
        return
    core_problems = CoreProblem.query.filter_by(oj_name=contest.clone_name).all()

    contest_json = core_contest.to_json()
    problems = list(p.to_json() for p in core_problems)
    contest.title = contest_json.get("title", "")
    contest.public = contest_json.get("public", False)
    contest.status = contest_json.get("status", "Pending")
    start_time = contest_json.get("start_time", 0)
    end_time = contest_json.get("end_time", 0)
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


@celery.task(bind=True, name="refresh_recent_contest")
def refresh_recent_contest(self):
    last = redis_con.get("vjudge-last-refresh-recent-contest") or 0
    last = datetime.fromtimestamp(float(last))
    if datetime.now() - last >= timedelta(hours=1):
        update_recent_contest()
        redis_con.set("vjudge-last-refresh-recent-contest", datetime.now().timestamp())
    contests = Contest.query.all()
    for contest in contests:
        if contest.status != "Ended" and contest.start_time - timedelta(
            hours=6
        ) <= datetime.utcnow() <= contest.start_time + timedelta(hours=6):
            refresh_contest_info.delay(contest.id)


def update_recent_contest():
    c = contest_clients.get("hdu")
    if c is None:
        return
    result = c.get_recent_contest()
    contests = [x.to_json() for x in result]
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


@celery.task(name="refresh_problem_all")
def refresh_problem_all():
    redis_con.lpush(
        "vjudge-crawler-tasks",
        json.dumps({"oj_name": "scu", "type": "problem", "all": True}),
    )
    redis_con.lpush(
        "vjudge-crawler-tasks",
        json.dumps({"oj_name": "hdu", "type": "problem", "all": True}),
    )


@celery.task(name="update_problem_all")
def update_problem_all():
    page = 1
    while True:
        pagination = CoreProblem.query.filter(
            or_(CoreProblem.oj_name == "scu", CoreProblem.oj_name == "hdu")
        ).paginate(page=page, per_page=100, error_out=False)
        if len(pagination.items) == 0:
            break
        for core_problem in pagination.items:
            try_update_problem(core_problem.oj_name, core_problem.problem_id)
        page += 1
