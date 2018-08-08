from datetime import datetime

from flask import current_app, render_template, request, flash, redirect, abort, url_for
from flask_login import login_required, current_user
from sqlalchemy import func

from . import contest
from .forms import SubmitProblemForm
from .. import tasks
from ..models import db, Problem, Contest, ContestSubmission, User, Permission


@contest.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config.get('FLASKY_FOLLOWERS_PER_PAGE', 20)
    pagination = Contest.query.order_by(Contest.id.desc()).paginate(page, per_page=per_page, error_out=False)
    return render_template('contest_list.html', contests=pagination.items,
                           endpoint='.index', pagination=pagination)


@contest.route('/submit/', methods=['POST'])
@login_required
def submit():
    langs = ['C', 'C++', 'Java']
    form = SubmitProblemForm([(name, name) for name in langs])
    if not form.validate_on_submit():
        abort(403)
    contest_id = form.contest_id.data
    problem_id = form.problem_id.data
    c = Contest.query.get(int(contest_id))
    result = c.get_ori_problem(problem_id)
    if result is None:
        abort(404)
    oj_name, real_pid = result
    language = form.language.data
    if Problem.query.filter_by(oj_name=oj_name, problem_id=real_pid).first() is None or language not in langs:
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
def problem(contest_id, problem_id):
    c = Contest.query.get(int(contest_id))
    if c is None:
        abort(404)
    result = c.get_ori_problem(problem_id)
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
            user_id=current_user.id, oj_name=oj_name, problem_id=real_pid).order_by(
            ContestSubmission.id.desc()).first()
        if res:
            source_code = res.code
            language = res.lang
    return render_template('contest_problem.html', problem=problem, form=form, source_code=source_code,
                           language=language, contest=c)


@contest.route('/<contest_id>/problem')
def problem_list(contest_id):
    c = Contest.query.get(int(contest_id))
    if c is None:
        abort(404)
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config.get('FLASKY_FOLLOWERS_PER_PAGE', 20)
    pagination = Problem.query.filter_by(oj_name=c.clone_name). \
        paginate(page, per_page=per_page, error_out=False)
    return render_template('contest_problem_list.html', problems=pagination.items, contest=c,
                           endpoint='.problem_list', pagination=pagination)


@contest.route('/<contest_id>/status')
def status(contest_id):
    c = Contest.query.get(int(contest_id))
    if c is None:
        abort(404)
    id = request.args.get('id', None, type=int)
    username = request.args.get('user')
    verdict = request.args.get('verdict', None)
    page = request.args.get('page', None, type=int)

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
        if u is not None:
            name = u.username
        else:
            name = ''
        submissions.append({'username': name, 'data': item})

    return render_template('contest_status.html', submissions=submissions, contest=c,
                           endpoint='.status', pagination=pagination)


@contest.route('/<contest_id>/ranklist')
def rank_list(contest_id):
    return ''


# @contest.route('/ranklist')
# def rank_list():
#     username = request.args.get('user')
#     page = request.args.get('page', None, type=int)
#     per_page = current_app.config.get('FLASKY_FOLLOWERS_PER_PAGE', 20)
#     if username == '':
#         return redirect(url_for('.rank_list'))
#     if username and page:
#         return redirect(url_for('.rank_list', user=username))
#
#     page = page if page else 1
#     if username:
#         pagination = User.query.filter_by(username=username).order_by(User.solved.desc()). \
#             order_by(User.submitted).paginate(page, per_page=per_page, error_out=False)
#     else:
#         pagination = User.query.order_by(User.solved.desc()).order_by(User.submitted). \
#             paginate(page, per_page=per_page, error_out=False)
#
#     users = []
#     rank = (page - 1) * per_page + 1
#     for item in pagination.items:
#         users.append({'rank': rank, 'username': item.username, 'solved': item.solved, 'submitted': item.submitted,
#                       'last_seen': item.last_seen})
#         rank += 1
#     return render_template('rank_list.html', users=users, endpoint='.rank_list', pagination=pagination)
#
#
@contest.route('/<contest_id>/source')
@login_required
def source_code(contest_id):
    c = Contest.query.get(int(contest_id))
    if c is None:
        abort(404)
    run_id = request.args.get('id', None, type=int)
    if not run_id:
        abort(404)
    submission = ContestSubmission.query.filter_by(contest_id=c.id, seq=run_id).first()
    if not submission:
        abort(404)
    if (not current_user.can(Permission.ADMINISTER) and
            not submission.share and submission.user_id != current_user.id):
        abort(403)
    if (not current_user.can(Permission.ADMINISTER) and
            submission.share and datetime.utcnow() < c.end_time):
        abort(403)
    u = User.query.get(submission.user_id)
    username = u.username if u else ''
    language = 'c_cpp'
    if submission.language == 'Java':
        language = 'java'
    return render_template('contest_source_code.html', contest=c, submission=submission, username=username,
                           language=language)
