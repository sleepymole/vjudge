import time

import argparse
import shlex
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('-b', required=False, dest='address', default='localhost:8000', help='address to bind')
args = parser.parse_args()

flask_process = subprocess.Popen(shlex.split(f"gunicorn -w 2 -k gevent manage:app -b '{args.address}'"))
celery_process = subprocess.Popen(shlex.split('celery worker --app=manage.celery -l info --concurrency=8 --beat'))

try:
    while True:
        time.sleep(3600)
        if flask_process.poll() == 0:
            flask_process = subprocess.Popen(shlex.split(f"gunicorn -w 2 -k gevent manage:app -b '{args.address}'"))
        if celery_process.poll() == 0:
            celery_process = subprocess.Popen(
                shlex.split('celery worker --app=manage.celery -l info --concurrency=8 --beat'))
except KeyboardInterrupt:
    flask_process.terminate()
    celery_process.terminate()
    flask_process.wait()
    celery_process.wait()
