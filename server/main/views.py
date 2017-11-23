import time
from flask import render_template, request, jsonify
from config import AVAILABLE_OJS
from .. import db, submit_queue
from ..models import Submission
from . import main


@main.route('/')
def index():
    return render_template('index.html')


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
