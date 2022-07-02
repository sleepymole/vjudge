import argparse
import shlex
import subprocess

from config import logger
from core.vjudge import VJudge

parser = argparse.ArgumentParser()
parser.add_argument(
    "-b",
    required=False,
    dest="address",
    default="localhost:8000",
    help="address to bind",
)
args = parser.parse_args()

flask_process = subprocess.Popen(
    shlex.split(f"gunicorn -w 2 -k gevent app:app -b '{args.address}'")
)
celery_process = subprocess.Popen(
    shlex.split("celery --app=app.celery worker -l info --concurrency=8 --beat")
)

try:
    vjudge = VJudge()
    vjudge.start()
except KeyboardInterrupt:
    logger.info("VJudge exiting")
finally:
    flask_process.terminate()
    celery_process.terminate()
    flask_process.wait()
    celery_process.wait()
