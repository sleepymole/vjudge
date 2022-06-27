import json
from datetime import datetime, timedelta

import redis
from flask import Flask, jsonify, request, abort, url_for
from sqlalchemy import and_, or_

from config import REDIS_CONFIG
from vjudge.models import db, Submission, Problem, Contest
from vjudge.site import contest_clients, supported_sites, supported_contest_sites

app = Flask(__name__)

redis_con = redis.StrictRedis(host=REDIS_CONFIG['host'], port=REDIS_CONFIG['port'], db=REDIS_CONFIG['db'])
submitter_queue = REDIS_CONFIG['queue']['submitter_queue']
crawler_queue = REDIS_CONFIG['queue']['crawler_queue']


@app.route('/problems/')
def get_problem_list():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    oj_name = request.args.get('oj_name', '')
    problem_id = request.args.get('problem_id', '')
    if oj_name:
        oj_name_filter = Problem.oj_name == oj_name
    else:
        filter_args = []
        for site in supported_sites:
            filter_args.append(Problem.oj_name == site)
        oj_name_filter = or_(*filter_args)
    pagination = Problem.query.filter(
        and_(oj_name_filter, Problem.problem_id.like(problem_id or '%'))).paginate(
        page=page, per_page=per_page, error_out=False)
    problems = pagination.items
    page = pagination.page
    prev = None
    if pagination.has_prev:
        prev = url_for('get_problem_list', oj_name=oj_name, problem_id=problem_id,
                       page=page - 1, per_page=per_page, _external=True)
    next = None
    if pagination.has_next:
        next = url_for('get_problem_list', oj_name=oj_name, problem_id=problem_id,
                       page=page + 1, per_page=per_page, _external=True)
    return jsonify({
        'problems': [p.summary() for p in problems],
        'prev': prev,
        'next': next,
        'count': pagination.total
    })


@app.route('/problems/', methods=['POST'])
def refresh_all_problems():
    oj_name = request.form.get('oj_name')
    if oj_name is None:
        return jsonify({'error': 'missing field oj_name'}), 422
    if oj_name not in supported_sites:
        return jsonify({'error': f'oj {oj_name} is not supported'}), 422
    redis_con.lpush(crawler_queue, json.dumps({
        'oj_name': oj_name,
        'type': 'problem',
        'all': True
    }))
    return jsonify({'status': 'success'})


@app.route('/problems/<oj_name>/<problem_id>')
def get_problem(oj_name, problem_id):
    problem = Problem.query.filter_by(oj_name=oj_name, problem_id=problem_id).first()
    if problem is None:
        abort(404)
    if datetime.utcnow() - timedelta(days=1) > problem.last_update:
        redis_con.lpush(crawler_queue, json.dumps({
            'oj_name': oj_name,
            'type': 'problem',
            'all': False,
            'problem_id': problem_id
        }))
    return jsonify(problem.to_json())


@app.route('/problems/<oj_name>/<problem_id>', methods=['POST'])
def refresh_problem(oj_name, problem_id):
    redis_con.lpush(crawler_queue, json.dumps({
        'oj_name': oj_name,
        'type': 'problem',
        'all': False,
        'problem_id': problem_id
    }))
    return jsonify({
        'status': 'success',
        'url': url_for('get_problem', oj_name=oj_name, problem_id=problem_id, _external=True)
    })


@app.route('/submissions/')
def get_submission_list():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    pagination = Submission.query.order_by(Submission.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    submissions = pagination.items
    page = pagination.page
    prev = None
    if pagination.has_prev:
        prev = url_for('get_submission_list', page=page - 1, per_page=per_page, _external=True)
    next = None
    if pagination.has_next:
        next = url_for('get_submission_list', page=page + 1, per_page=per_page, _external=True)
    return jsonify({
        'submissions': [s.to_json() for s in submissions],
        'prev': prev,
        'next': next,
        'count': pagination.total
    })


@app.route('/submissions/', methods=['POST'])
def submit_problem():
    oj_name = request.form.get('oj_name')
    problem_id = request.form.get('problem_id')
    language = request.form.get('language')
    source_code = request.form.get('source_code')
    if None in (oj_name, problem_id, language, source_code):
        return jsonify({'error': 'missing field'}), 422
    if not Problem.query.filter_by(oj_name=oj_name, problem_id=problem_id).first():
        return jsonify({'error': 'no such problem'}), 422
    submission = Submission(oj_name=oj_name, problem_id=problem_id,
                            language=language, source_code=source_code)
    db.session.add(submission)
    db.session.commit()
    redis_con.lpush(submitter_queue, submission.id)
    url = url_for('get_submission', id=submission.id, _external=True)
    return jsonify({'status': 'success', 'id': submission.id, 'url': url})


@app.route('/submissions/<id>')
def get_submission(id):
    submission = Submission.query.get(id)
    if submission is None:
        abort(404)
    return jsonify(submission.to_json())


@app.route('/submissions/<id>', methods=['POST'])
def update_submission(id):
    submission = Submission.query.get(id)
    if submission is None:
        return jsonify({'error': 'no such submission'}), 422
    if submission.verdict not in ('Queuing', 'Being Judged'):
        submission.verdict = 'Being Judged'
        db.session.commit()
        redis_con.lpush(submitter_queue, submission.id)
    url = url_for('get_submission', id=submission.id, _external=True)
    return jsonify({'status': 'success', 'id': submission.id, 'url': url})


@app.route('/contests/<site>')
def get_recent_contests(site):
    if site not in contest_clients:
        abort(404)
    c = contest_clients[site]
    contest_list = c.get_recent_contest()
    return jsonify({
        'contests': [x.to_json() for x in contest_list]
    })


@app.route('/contests/<site>/<contest_id>')
def get_contest_info(site, contest_id):
    contest = Contest.query.filter_by(site=site, contest_id=contest_id).first()
    if contest is None:
        abort(404)
    problems = Problem.query.filter_by(oj_name=contest.oj_name).all()
    return jsonify({
        'contest': contest.to_json(),
        'problems': [p.to_json() for p in problems]
    })


@app.route('/contests/<site>/<contest_id>', methods=['POST'])
def crawl_contest_info(site, contest_id):
    if site not in supported_contest_sites:
        return jsonify({'error': f'site {site} is not supported'}), 422
    redis_con.lpush(crawler_queue, json.dumps({
        'oj_name': f'{site}_ct_{contest_id}',
        'type': 'contest'
    }))
    url = url_for('get_contest_info', site=site, contest_id=contest_id, _external=True)
    return jsonify({'status': 'success', 'url': url})


@app.teardown_appcontext
def shutdown_session(response_or_exc):
    db.session.remove()
    return response_or_exc


@app.errorhandler(404)
def page_not_found(e):
    return jsonify({'error': 'not found'}), 404


@app.errorhandler(500)
def internal_server_error(e):
    return jsonify({'error': 'internal_server_error'}), 500
