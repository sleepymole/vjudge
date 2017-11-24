import time
from flask import render_template, request, jsonify, flash, redirect, abort, url_for
from flask_login import login_required, current_user
from config import AVAILABLE_OJS
from .forms import EditProfileForm, EditProfileAdminForm
from .. import db, submit_queue
from ..models import User, Role, Permission, Submission
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


@main.route('/edit_profile', methods=['GET', 'POST'])
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
    form.name.data = current_user.name
    form.email.data = current_user.email
    form.location.data = current_user.location
    form.about_me.data = current_user.about_me
    return render_template('edit_profile.html', form=form)


@main.route('/edit-profile/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_profile_admin(id):
    user = User.query.get(id)
    if user is None:
        abort(404)
    form = EditProfileAdminForm(user=user)
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
    if current_user.is_following(user):
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
    return redirect(url_for('.user', username=username))


@main.route('/followed-by/<username>')
def followed_by(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('Invalid user.')
        return redirect(url_for('.index'))
    return redirect(url_for('.user', username=username))


@main.route('/submit', methods=['POST'])
def submit():
    oj_name = request.form.get('oj_name')
    problem_id = request.form.get('problem_id')
    language = request.form.get('language')
    source_code = request.form.get('source_code')
    if None in (oj_name, problem_id, language, source_code) or oj_name not in AVAILABLE_OJS:
        return jsonify({'status': 'failed'})
    submission = Submission(oj_name=oj_name, problem_id=problem_id,
                            language=language, source_code=source_code, submit_time=int(time.time()))
    db.session.add(submission)
    db.session.commit()
    run_id = submission.run_id
    submit_queue.put(run_id)
    return jsonify({'status': 'success', 'run_id': run_id})


@main.route('/status/<run_id>')
def status(run_id):
    result = db.session.query(Submission.verdict, Submission.exe_time, Submission.exe_mem). \
        filter_by(run_id=run_id).one()
    if result is None:
        return jsonify({'status': 'failed'})
    return jsonify({'status': 'success', 'result': list(result)})
