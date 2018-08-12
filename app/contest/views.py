from datetime import datetime

from flask import current_app, render_template, request, flash, redirect, abort, url_for, g
from flask_login import login_required, current_user
from sqlalchemy import func

from . import contest
from .forms import SubmitProblemForm
from .utlis import contest_check
from .. import tasks
from ..models import db, Problem, Contest, ContestSubmission, User, Permission

supported_languages = ['C', 'C++', 'Java']


@contest.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config.get('FLASKY_FOLLOWERS_PER_PAGE', 20)
    pagination = Contest.query.order_by(Contest.id.desc()).paginate(page, per_page=per_page, error_out=False)
    return render_template('contest/index.html', contests=pagination.items,
                           endpoint='.index', pagination=pagination)


@contest.route('/submit/', methods=['POST'])
@login_required
def submit():
    form = SubmitProblemForm([(name, name) for name in supported_languages])
    if not form.validate_on_submit():
        abort(403)
    contest_id = form.contest_id.data
    problem_id = form.problem_id.data
    c = Contest.query.get(int(contest_id))
    if datetime.utcnow() < c.start_time:
        flash('Contest has not begin yet.')
        return redirect(url_for('.problem', contest_id=contest_id, problem_id=problem_id))
    if datetime.utcnow() > c.end_time:
        flash('Contest is over.')
        return redirect(url_for('.problem', contest_id=contest_id, problem_id=problem_id))
    result = c.get_ori_problem(problem_id)
    if result is None:
        abort(404)
    oj_name, real_pid = result
    language = form.language.data
    if not (Problem.query.filter_by(oj_name=oj_name, problem_id=real_pid).first() or
            language not in supported_languages):
        abort(404)
    code = form.source_code.data
    if len(code) < 50 or len(code) > 65536:
        flash('Make sure your code length is longer than 50 and not exceed 65536 Bytes.')
        return redirect(url_for('.problem', contest_id=contest_id, problem_id=problem_id))
    share = form.share.data
    max_seq = db.session.query(func.max(ContestSubmission.seq)).first()[0] or 0
    submission = ContestSubmission(user_id=current_user.id, seq=max_seq + 1, contest_id=contest_id, oj_name=oj_name,
                                   problem_id=real_pid, language=language, source_code=code, share=share)
    db.session.add(submission)
    db.session.commit()
    tasks.submit_problem.delay(submission.id, in_contest=True)
    return redirect(url_for('.status', contest_id=submission.contest_id))


@contest.route('/<contest_id>/problem/<problem_id>')
@contest_check
def problem(contest_id, problem_id):
    contest = g.contest
    result = contest.get_ori_problem(problem_id)
    if result is None:
        abort(404)
    oj_name, real_pid = result
    problem = Problem.query.filter_by(oj_name=oj_name, problem_id=real_pid).first()
    if problem is None:
        abort(404)
    form = SubmitProblemForm()
    form.contest_id.data = contest_id
    form.problem_id.data = problem_id
    source_code = ''
    language = 'C++'
    if current_user.is_authenticated:
        res = db.session.query(ContestSubmission.source_code.label('code'),
                               ContestSubmission.language.label('lang')).filter_by(
            user_id=current_user.id, contest_id=contest.id, oj_name=oj_name, problem_id=real_pid).order_by(
            ContestSubmission.id.desc()).first()
        if res:
            source_code = res.code
            language = res.lang

    return render_template('contest/problem.html', contest=contest, problem=problem, form=form,
                           source_code=source_code, language=language)


@contest.route('/<contest_id>/problem')
@contest_check
def problem_list(contest_id):
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config.get('FLASKY_FOLLOWERS_PER_PAGE', 20)
    contest = g.contest
    pagination = Problem.query.filter_by(oj_name=contest.clone_name).order_by(Problem.problem_id).paginate(
        page, per_page=per_page, error_out=False)
    return render_template('contest/problem_list.html', contest=contest, problems=pagination.items,
                           endpoint='.problem_list', pagination=pagination)


@contest.route('/<contest_id>/status')
@contest_check
def status(contest_id):
    id = request.args.get('id', None, type=int)
    username = request.args.get('user')
    verdict = request.args.get('verdict', None)
    page = request.args.get('page', None, type=int)
    contest = g.contest

    query_dict = dict(seq=id, username=username, verdict=verdict, page=page)

    query_args = {}
    for k in query_dict:
        if query_dict[k] is not None:
            query_args[k] = query_dict[k]
    query_args['contest_id'] = contest_id

    page = page if page else 1
    if 'page' in query_args:
        query_args.pop('page')
    per_page = current_app.config.get('FLASKY_FOLLOWERS_PER_PAGE', 20)

    if 'username' in query_args:
        username = query_args.pop('username')
        query_args['user_id'] = db.session.query(
            User.id.label('user_id')).filter_by(username=username).first().user_id

    pagination = ContestSubmission.query.filter_by(**query_args).order_by(
        ContestSubmission.id.desc()).paginate(page, per_page=per_page, error_out=False)
    submissions = []
    for item in pagination.items:
        u = User.query.get(item.user_id)
        name = u.username if u is not None else ''
        submissions.append({'username': name, 'data': item})

    return render_template('contest/status.html', contest=contest, submissions=submissions,
                           endpoint='.status', pagination=pagination)


@contest.route('/<contest_id>/ranklist')
@contest_check
def rank_list(contest_id):
    contest = g.contest
    return render_template('contest/rank_list.html', contest=contest)


@contest.route('/<contest_id>/source')
@contest_check
@login_required
def source_code(contest_id):
    contest = g.contest
    seq = request.args.get('id', 0, type=int)
    submission = ContestSubmission.query.filter_by(contest_id=contest.id, seq=seq).first()
    if not submission:
        abort(404)

    if (not current_user.can(Permission.ADMINISTER) and submission.user_id != current_user.user_id and
            (datetime.utcnow() < contest.end_time or not current_user.can(Permission.MODERATE)
             and not submission.share)):
        abort(403)

    u = User.query.get(submission.user_id)
    username = u.username if u else ''
    language = 'c_cpp'
    if submission.language == 'Java':
        language = 'java'
    return render_template('contest/source_code.html', contest=contest, submission=submission,
                           username=username, language=language)
