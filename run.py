import shlex
import subprocess
import time

flask_process = subprocess.Popen(shlex.split('gunicorn -w 2 -k gevent manage:app'))
celery_process = subprocess.Popen(shlex.split('celery worker --app=manage.celery -l info --concurrency=4 --beat'))

try:
    while True:
        time.sleep(3600)
        if flask_process.poll() == 0:
            flask_process = subprocess.Popen(shlex.split('gunicorn -w 2 -k gevent manage:app'))
        if celery_process.poll() == 0:
            celery_process = subprocess.Popen(shlex.split('celery worker -l INFO -A manage.celery --beat'))
except KeyboardInterrupt:
    flask_process.terminate()
    celery_process.terminate()
    flask_process.wait()
    celery_process.wait()
