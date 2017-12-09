from flask import current_app, render_template, request, flash, redirect, abort, url_for
from flask_login import login_required, current_user
from sqlalchemy import and_
from .forms import EditProfileForm, EditProfileAdminForm, SubmitProblemForm, EditProblemForm
from ..models import db, User, Role, Permission, Problem, Submission
from ..decorators import admin_required, permission_required
from . import main
from .. import tasks
from bs4 import BeautifulSoup


@main.route('/')
def index():
    return render_template('index.html')


@main.route('/user/<username>')
def user(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        abort(404)
    return render_template('user.html', user=user)


@main.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm()
    if form.validate_on_submit():
        current_user.name = form.name.data
        current_user.email = form.email.data
        current_user.location = form.location.data
        current_user.about_me = form.about_me.data
        db.session.add(current_user)
        flash('Your profile has been updated.')
        return redirect(url_for('.user', username=current_user.username))
    form.username.data = current_user.username
    form.name.data = current_user.name
    form.email.data = current_user.email
    form.location.data = current_user.location
    form.about_me.data = current_user.about_me
    return render_template('edit_profile.html', form=form, user=current_user)


@main.route('/edit-profile/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_profile_admin(id):
    user = User.query.get(id)
    if user is None:
        abort(404)
    form = EditProfileAdminForm()
    if form.validate_on_submit():
        user.username = form.username.data
        user.role = Role.query.get(form.role.data)
        user.name = form.name.data
        user.email = form.email.data
        user.location = form.location.data
        user.about_me = form.about_me.data
        db.session.add(user)
        flash('The profile has been updated.')
        return redirect(url_for('.user', username=user.username))
    form.username.data = user.username
    form.role.data = user.role_id
    form.name.data = user.name
    form.email.data = user.email
    form.location.data = user.location
    form.about_me.data = user.about_me
    return render_template('edit_profile.html', form=form, user=user)


@main.route('/follow/<username>')
@login_required
@permission_required(Permission.FOLLOW)
def follow(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('Invalid user.')
        return redirect(url_for('.index'))
    if current_user.id == user.id:
        flash('You can not follow yourself.')
        return redirect(url_for('.user', username=username))
    if current_user.is_following(user):
        flash('You are already following this user.')
        return redirect(url_for('.user', username=username))
    current_user.follow(user)
    flash('You are now following {}'.format(username))
    return redirect(url_for('.user', username=username))


@main.route('/unfollow/<username>')
@login_required
@permission_required(Permission.FOLLOW)
def unfollow(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('Invalid user.')
        return redirect(url_for('.index'))
    if not current_user.is_following(user):
        flash('You are not following this user.')
        return redirect(url_for('.user', username=username))
    current_user.unfollow(user)
    flash('You are not following {} anymore.'.format(username))
    return redirect(url_for('.user', username=username))


@main.route('/followers/<username>')
def followers(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('Invalid user.')
        return redirect(url_for('.index'))
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config.get('FLASKY_FOLLOWERS_PER_PAGE', 20)
    pagination = user.followers.paginate(page, per_page=per_page, error_out=False)
    follows = [{'user': item.follower, 'timestamp': item.timestamp} for item in pagination.items]
    return render_template('followers.html', user=user, title='Followers of',
                           endpoint='.followers', pagination=pagination, follows=follows)


@main.route('/followed-by/<username>')
def followed_by(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('Invalid user.')
        return redirect(url_for('.index'))
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config.get('FLASKY_FOLLOWERS_PER_PAGE', 20)
    pagination = user.followed.paginate(page, per_page=per_page, error_out=False)
    follows = [{'user': item.followed, 'timestamp': item.timestamp} for item in pagination.items]
    return render_template('followers.html', user=user, title='Followed by',
                           endpoint='.followed_by', pagination=pagination, follows=follows)


@main.route('/problem/<oj_name>/')
@main.route('/problem/<oj_name>/<problem_id>')
def problem(oj_name, problem_id=None):
    if not problem_id:
        return redirect(url_for('.problem_list', oj=oj_name))
    problem = Problem.query.filter_by(oj_name=oj_name, problem_id=problem_id).first()
    if problem is None:
        abort(404)
    form = SubmitProblemForm()
    form.oj_name.data = oj_name
    form.problem_id.data = problem_id
    return render_template('problem.html', problem=problem, form=form)


@main.route('/problem')
def problem_list():
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


@main.route('/edit-problem/<oj_name>/<problem_id>', methods=['GET', 'POST'])
@permission_required(Permission.MODERATE)
def edit_problem(oj_name, problem_id):
    problem = Problem.query.filter_by(oj_name=oj_name, problem_id=problem_id).first()
    if not problem:
        abort(404)
    form = EditProblemForm()
    if form.validate_on_submit():
        problem.description = form.description.data
        problem.input = form.input.data
        problem.output = form.output.data
        problem.sample_input = '<pre>{}</pre>'.format(form.sample_input.data)
        problem.sample_output = '<pre>{}</pre>'.format(form.sample_output.data)
        db.session.add(problem)
        flash('The problem has been updated.')
        return redirect(url_for('.edit_problem', oj_name=oj_name, problem_id=problem_id))
    sample_input = BeautifulSoup(problem.sample_input, 'lxml').text if problem.sample_input else ''
    sample_output = BeautifulSoup(problem.sample_output, 'lxml').text if problem.sample_output else ''
    return render_template('edit_problem.html', problem=problem, sample_input=sample_input,
                           sample_output=sample_output, form=form)


@main.route('/refresh-problem/<oj_name>/<problem_id>', methods=['POST'])
@permission_required(Permission.MODERATE)
def refresh_problem(oj_name, problem_id):
    tasks.refresh_problem.delay(oj_name=oj_name, problem_id=problem_id)
    return ''


@main.route('/submit', methods=['POST'])
@login_required
def submit():
    langs = ['C', 'C++', 'Java']
    form = SubmitProblemForm([(name, name) for name in langs])
    if not form.validate_on_submit():
        abort(403)
    oj_name = form.oj_name.data
    problem_id = form.problem_id.data
    language = form.language.data
    if Problem.query.filter_by(oj_name=oj_name, problem_id=problem_id).first() is None \
            or language not in langs:
        abort(404)
    source_code = form.source_code.data
    if len(source_code) < 50 or len(source_code) > 65536:
        flash('Make sure your code length is longer than 50 and not exceed 65536 Bytes.')
        return redirect(url_for('.problem', oj_name=oj_name, problem_id=problem_id))
    share = form.share.data
    submission = Submission(user_id=current_user.id, oj_name=oj_name, problem_id=problem_id, language=language,
                            source_code=source_code, share=share)
    db.session.add(submission)
    db.session.commit()
    tasks.submit_problem.delay(submission.id)
    return redirect(url_for('.status'))


@main.route('/status')
def status():
    id = request.args.get('id', None, type=int)
    username = request.args.get('user')
    oj_name = request.args.get('oj', None)
    if oj_name == 'all':
        oj_name = None
    problem_id = request.args.get('problem_id', None)
    page = request.args.get('page', None, type=int)
    query = request.args.get('query', None)

    query_dict = dict(id=id, username=username, oj_name=oj_name, problem_id=problem_id, page=page)
    if query:
        words = query.split()
        for word in words:
            if User.query.filter_by(username=word).first():
                query_dict['username'] = word
            elif Problem.query.filter_by(problem_id=word).first():
                query_dict['problem_id'] = word

    query_args = {}
    for k in query_dict:
        if query_dict[k]:
            query_args[k] = query_dict[k]

    kwargs = query_args.copy()
    if 'username' in kwargs:
        kwargs['user'] = kwargs.pop('username')
    if 'oj_name' in kwargs:
        kwargs['oj'] = kwargs.pop('oj_name')

    if len(kwargs) != len(request.args):
        return redirect(url_for('.status', **kwargs))
    for k in kwargs:
        if k not in request.args or kwargs[k] != request.args.get(k):
            return redirect(url_for('.status', **kwargs))

    page = page if page else 1
    if 'page' in query_args:
        query_args.pop('page')
    per_page = current_app.config.get('FLASKY_FOLLOWERS_PER_PAGE', 20)

    if 'username' in query_args:
        username = query_args.pop('username')
        pagination = Submission.query.filter_by(**query_args).filter(User.username == username).order_by(
            Submission.id.desc()).paginate(page, per_page=per_page, error_out=False)
    else:
        pagination = Submission.query.filter_by(**query_args).order_by(Submission.id.desc()). \
            paginate(page, per_page=per_page, error_out=False)
    submissions = [{'username': item.user.username, 'data': item} for item in pagination.items]
    return render_template('status.html', submissions=submissions, endpoint='.status', pagination=pagination)
