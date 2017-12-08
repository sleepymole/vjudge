import shlex
import subprocess
import time

flask_process = subprocess.Popen(shlex.split('gunicorn -w 2 --threads 10 manage:app'))
celery_process = subprocess.Popen(shlex.split('celery worker -l INFO -A manage.celery'))

while True:
    time.sleep(3600)
    if flask_process.poll() == 0:
        flask_process = subprocess.Popen(shlex.split('gunicorn -w 2 --threads 10 manage:app'))
    if celery_process.poll() == 0:
        celery_process = subprocess.Popen(shlex.split('celery worker -l INFO -A manage.celery'))
