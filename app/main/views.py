from flask import current_app, render_template, request, flash, redirect, abort, url_for
from flask_login import login_required, current_user
from sqlalchemy import and_
from .forms import EditProfileForm, EditProfileAdminForm, SubmitProblemForm
from ..models import db, User, Role, Permission, Problem
from ..decorators import admin_required, permission_required
from . import main


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
    pagination = Problem.query.filter(
        and_(Problem.oj_name.like(oj_name or '%'),
             Problem.problem_id.like(problem_id or '%'))). \
        paginate(page, per_page=per_page, error_out=False)
    problems = [{'oj_name': item.oj_name, 'problem_id': item.problem_id, 'title': item.title,
                 'last_update': item.last_update} for item in pagination.items]
    return render_template('problem_list.html', problems=problems, endpoint='.problem_list',
                           pagination=pagination, oj=oj_name)


@main.route('/edit-problem/<oj_name>/<problem_id>')
@permission_required(Permission.MODERATE)
def edit_problem(oj_name, problem_id):
    problem = Problem.query.filter_by(oj_name=oj_name, problem_id=problem_id).first()
    if not problem:
        abort(404)
    return render_template('edit_problem.html')


@main.route('/refresh-problem/<oj_name>/<problem_id>', methods=['POST'])
@permission_required(Permission.MODERATE)
def refresh_problem(oj_name, problem_id):
    return ''


@main.route('/submit', methods=['POST'])
@login_required
def submit():
    form = SubmitProblemForm([('C', 'C'), ('C++', 'C++'), ('Java', 'Java')])
    if not form.validate_on_submit():
        abort(403)
    return redirect('http://127.0.0.1:5000/problem/hdu/6242')
