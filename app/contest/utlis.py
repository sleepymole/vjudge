from functools import wraps

from flask import abort, g

from ..models import Contest


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
