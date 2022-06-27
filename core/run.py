import argparse
import shlex
import subprocess

from config import get_accounts, logger, LOG_LEVEL
from vjudge.main import VJudge

parser = argparse.ArgumentParser()
parser.add_argument('-b', required=False, dest='address', default='localhost:5000', help='address to bind')
args = parser.parse_args()

p = subprocess.Popen(
    shlex.split(f"gunicorn -w 2 -k gevent --logger-class config.GLogger --log-level {LOG_LEVEL} "
                f"-b '{args.address}' manage:app"))

try:
    normal_accounts, contest_accounts = get_accounts()
    vjudge = VJudge(normal_accounts=normal_accounts, contest_accounts=contest_accounts)
    vjudge.start()
except KeyboardInterrupt:
    logger.info('VJudge exiting')
finally:
    p.terminate()
    p.wait()
