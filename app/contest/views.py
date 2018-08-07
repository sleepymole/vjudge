from flask import current_app, render_template, request, flash, redirect, abort, url_for
from flask_login import login_required, current_user
from sqlalchemy import and_, func

from . import contest
from .forms import SubmitProblemForm
from .. import tasks
from ..models import db, Problem, Submission, Contest, ContestSubmission


@contest.route('/')
def index():
    return render_template('index.html')


@contest.route('/submit/', methods=['POST'])
@login_required
def submit():
    langs = ['C', 'C++', 'Java']
    form = SubmitProblemForm([(name, name) for name in langs])
    if not form.validate_on_submit():
        abort(403)
    contest_id = form.contest_id.data
    problem_id = form.problem_id.data
    c = Contest.query.get(int(contest_id)).first()
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
        # TODO
        return redirect(url_for('.problem', oj_name=oj_name, problem_id=problem_id))
    share = form.share.data
    max_seq = db.session.query(func.max(ContestSubmission.seq)).first()[0] or 0
    submission = ContestSubmission(user_id=current_user.id, seq=max_seq + 1, contest_id=contest_id, oj_name=oj_name,
                                   problem_id=real_pid, language=language, source_code=code, share=share)
    db.session.add(submission)
    db.session.commit()
    tasks.submit_problem.delay(submission.id, in_contest=True)
    return redirect(url_for('.status'))


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
        res = db.session.query(Submission.source_code.label('code'), Submission.language.label('lang')). \
            filter_by(user_id=current_user.id, oj_name=oj_name, problem_id=problem_id).order_by(
            Submission.id.desc()).first()
        if res:
            source_code = res.code
            language = res.lang
    return render_template('problem.html', problem=problem, form=form, source_code=source_code, language=language)


@contest.route('/<contest_id>/problem')
def problem_list(contest_id):
    oj_name = request.args.get('oj', None)
    problem_id = request.args.get('problem_id', None)
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config.get('FLASKY_FOLLOWERS_PER_PAGE', 20)
    kwargs = dict(request.args)
    for k in kwargs:
        kwargs[k] = kwargs[k][0]
    need_redirect = False
    if oj_name == 'all':
        kwargs.pop('oj')
        need_redirect = True
    if problem_id == '':
        kwargs.pop('problem_id')
        need_redirect = True
    if need_redirect:
        return redirect(url_for('.problem_list', **kwargs))
    pagination = Problem.query.filter(
        and_(Problem.oj_name.like(oj_name or '%'),
             Problem.problem_id.like(problem_id or '%'))). \
        paginate(page, per_page=per_page, error_out=False)
    return render_template('problem_list.html', problems=pagination.items, endpoint='.problem_list',
                           pagination=pagination, oj=oj_name)

# @contest.route('/status')
# def status():
#     id = request.args.get('id', None, type=int)
#     username = request.args.get('user')
#     oj_name = request.args.get('oj', None)
#     if oj_name == 'all':
#         oj_name = None
#     problem_id = request.args.get('problem_id', None)
#     verdict = request.args.get('verdict', None)
#     page = request.args.get('page', None, type=int)
#     query = request.args.get('query', None)
#
#     query_dict = dict(id=id, username=username, oj_name=oj_name,
#                       problem_id=problem_id, verdict=verdict, page=page)
#     if query:
#         words = query.split()
#         for word in words:
#             if User.query.filter_by(username=word).first():
#                 query_dict['username'] = word
#             elif Problem.query.filter_by(problem_id=word).first():
#                 query_dict['problem_id'] = word
#             elif word.lower() == 'accepted':
#                 query_dict['verdict'] = 'Accepted'
#             elif word.lower() in ('scu', 'hdu'):
#                 query_dict['oj_name'] = word.lower()
#
#     query_args = {}
#     for k in query_dict:
#         if query_dict[k]:
#             query_args[k] = query_dict[k]
#
#     kwargs = query_args.copy()
#     if 'username' in kwargs:
#         kwargs['user'] = kwargs.pop('username')
#     if 'oj_name' in kwargs:
#         kwargs['oj'] = kwargs.pop('oj_name')
#     if 'page' in kwargs:
#         kwargs['page'] = str(kwargs['page'])
#
#     if len(kwargs) != len(request.args):
#         return redirect(url_for('.status', **kwargs))
#     for k in kwargs:
#         if k not in request.args or kwargs[k] != request.args.get(k):
#             return redirect(url_for('.status', **kwargs))
#
#     page = page if page else 1
#     if 'page' in query_args:
#         query_args.pop('page')
#     per_page = current_app.config.get('FLASKY_FOLLOWERS_PER_PAGE', 20)
#
#     if 'username' in query_args:
#         username = query_args.pop('username')
#         query_args['user_id'] = db.session.query(User.id.label('user_id')). \
#             filter_by(username=username).first().user_id
#
#     pagination = Submission.query.filter_by(**query_args).order_by(Submission.id.desc()). \
#         paginate(page, per_page=per_page, error_out=False)
#     submissions = [{'username': item.user.username, 'data': item} for item in pagination.items]
#
#     return render_template('status.html', submissions=submissions, endpoint='.status',
#                            pagination=pagination, oj=oj_name or 'all')
#
#
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
# @contest.route('/source')
# @login_required
# def source_code():
#     run_id = request.args.get('id', None, type=int)
#     if not run_id:
#         abort(404)
#     submission = Submission.query.get(run_id)
#     if not submission:
#         abort(404)
#     if not current_user.can(Permission.MODERATE) and \
#             not submission.share and submission.user_id != current_user.id:
#         abort(403)
#     username = submission.user.username
#     language = 'c_cpp'
#     if submission.language == 'Java':
#         language = 'java'
#     return render_template('source_code.html', submission=submission, username=username, language=language)
