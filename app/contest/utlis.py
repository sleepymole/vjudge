from datetime import timedelta
from functools import wraps

from flask import abort, g

from ..models import Contest, ContestSubmission, User


def contest_check(f):
    @wraps(f)
    def decorated_function(contest_id, *args, **kwargs):
        try:
            contest_id = int(contest_id)
        except ValueError:
            abort(403)
        contest = Contest.query.get(contest_id)
        if not contest:
            abort(404)
        g.contest = contest
        return f(contest_id, *args, **kwargs)

    return decorated_function


def generate_board():
    class Record(object):
        def __init__(self, user_id, penalty=timedelta(seconds=0), solved=0):
            self.user_id = user_id
            self.penalty = penalty
            self.solved = solved

        def __lt__(self, other):
            if self.solved != other.solved:
                return self.solved > other.solved
            return self.penalty < other.solved

        def __eq__(self, other):
            return self.solved == other.solved and self.penalty == other.penalty

    contest = g.contest
    records = {}
    submissions = ContestSubmission.query.all()
    for submission in submissions:
        record = records.get(submission.user_id, Record(user_id=submission.user_id))
        ac_tm, wa_cnt = getattr(record, submission.problem_id, (None, 0))
        if ac_tm is not None:
            continue
        if submission.verdict in ('Queuing', 'Being Judged', 'Submit Failed', 'Compilation Error'):
            continue
        if submission.verdict == 'Accepted':
            ac_tm = submission.time_stamp - contest.start_time
            record.penalty += ac_tm + wa_cnt * timedelta(minutes=20)
        else:
            wa_cnt += 1
        setattr(record, submission.problem_id, (ac_tm, wa_cnt))
    records = [records[u] for u in records]
    records.sort()
    board = []
    for record in records:
        u = User.query.get(int(record.user_id))
        username = u.username if u else ''
        data = {
            'username': username,
            'penalty': record.penalty,
            'solved': record.solved
        }
        problem_list = [pid for pid in contest.get_ori_problems()]
        for pid in problem_list:
            data[pid] = getattr(record, pid, (None, 0))
        board.append(data)
    return board
