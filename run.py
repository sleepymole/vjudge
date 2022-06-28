import argparse
import shlex
import subprocess

from core.backend import load_accounts
from core.vjudge import VJudge
from config import logger

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
    shlex.split(f"gunicorn -w 2 -k gevent manage:app -b '{args.address}'")
)
celery_process = subprocess.Popen(
    shlex.split("celery worker --app=manage.celery -l info --concurrency=8 --beat")
)

try:
    normal_accounts, contest_accounts = load_accounts()
    vjudge = VJudge(normal_accounts=normal_accounts, contest_accounts=contest_accounts)
    vjudge.start()
except KeyboardInterrupt:
    logger.info("VJudge exiting")
finally:
    flask_process.terminate()
    celery_process.terminate()
    flask_process.wait()
    celery_process.wait()
