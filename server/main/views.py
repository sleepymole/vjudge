import time
from flask import render_template, request, jsonify, flash, redirect, abort, url_for
from flask_login import login_required, current_user
from config import AVAILABLE_OJS
from .forms import EditProfileForm, EditProfileAdminForm
from .. import db, submit_queue
from ..models import User, Role, Submission
from ..decorators import admin_required
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
        current_user.location = form.location.data
        current_user.about = form.about_me.data
        db.session.add(current_user)
        flash('Your profile has been updated.')
        return redirect(url_for('.user', username=current_user.username))
    form.name.data = current_user.name
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
        user.confirmed = form.confirmed.data
        user.role = Role.query.get(form.role.data)
        user.name = form.name.data
        user.location = form.location.data
        user.about_me = form.about_me.data
        db.session.add(user)
        flash('The profile has been updated.')
        return redirect(url_for('.user', username=user.username))
    form.username.data = user.username
    form.confirmed.data = user.confirmed
    form.role.data = user.role_id
    form.name.data = user.name
    form.location.data = user.location
    form.about_me.data = user.about_me


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
