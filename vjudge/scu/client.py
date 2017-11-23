import requests
import sqlite3
import re
import os
from bs4 import BeautifulSoup
from ..base import BaseClient
from .. import exceptions

base_url = 'http://acm.scu.edu.cn/soj'
base_dir = os.path.abspath(os.path.dirname(__file__))
db = sqlite3.connect(os.path.join(base_dir, 'captcha.db'), check_same_thread=False)


class SOJClient(BaseClient):
    def __init__(self, auth=None, **kwargs):
        super().__init__()
        self.auth = auth
        self.timeout = kwargs.get('timeout', 5)
        if auth is not None:
            self.username, self.password = auth
            self.login(self.username, self.password)

    def login(self, username, password):
        url = base_url + '/login.action'
        data = {
            'back': 2,
            'id': username,
            'password': password,
            'submit': 'login'
        }
        try:
            r = self._session.post(url, data, timeout=self.timeout)
        except requests.exceptions.ConnectionError:
            raise exceptions.ConnectionError
        if re.search('USER_NOT_EXIST', r.text):
            raise exceptions.UserNotExist
        elif re.search('PASSWORD_ERROR', r.text):
            raise exceptions.PasswordError
        self.auth = (username, password)
        self.username = username
        self.password = password

    def check_login(self):
        url = base_url + '/update_user_form.action'
        try:
            r = self._session.get(url, timeout=self.timeout)
        except requests.exceptions.RequestException:
            raise exceptions.ConnectionError
        if re.search('Please login first', r.text):
            return False
        return True

    def update_cookies(self):
        if self.auth is None:
            raise exceptions.LoginRequired
        self.login(self.username, self.password)

    def get_problem(self, problem_id):
        pass

    def submit_problem(self, problem_id, language, source_code):
        if self.auth is None:
            raise exceptions.LoginRequired
        submit_url = base_url + '/submit.action'
        status_url = base_url + '/solutions.action?userId={}&problemId={}'. \
            format(self.username, problem_id)
        captcha = self._get_captcha()
        if captcha is None:
            raise exceptions.VJudgeException
        data = {
            'problemId': problem_id,
            'validation': captcha,
            'language': language,
            'source': source_code,
            'submit': 'Submit'
        }
        try:
            r = self._session.post(submit_url, data, timeout=self.timeout)
            if re.search('ERROR', r.text):
                if not self.check_login():
                    raise exceptions.LoginExpired
                else:
                    raise exceptions.SubmitError
            r = self._session.get(status_url, timeout=self.timeout)
        except requests.exceptions.RequestException:
            raise exceptions.ConnectionError
        soup = BeautifulSoup(r.text, 'lxml')
        try:
            tag = soup.find_all('table')[1].find_all('tr')[1]
            run_id = next(tag.stripped_strings)
        except IndexError:
            raise exceptions.SubmitError
        return run_id

    def get_submit_status(self, run_id, **kwargs):
        status_url = base_url + '/solutions.action?from=' + run_id
        try:
            r = self._session.get(status_url, timeout=self.timeout)
        except requests.exceptions.RequestException:
            raise exceptions.ConnectionError
        try:
            soup = BeautifulSoup(r.text, 'lxml')
            tag = soup.find_all('table')[1].find_all('tr')[1]
            col_tags = tag.find_all('td')
            result = [' '.join(x.stripped_strings) for x in col_tags[5:]]
            verdict, exe_time, exe_mem = result[0], int(result[1]), int(result[2])
            return verdict, exe_time, exe_mem
        except (IndexError, ValueError):
            pass

    def _get_captcha(self):
        url = os.path.join(base_url, 'validation_code')
        try:
            r = self._session.get(url, timeout=self.timeout)
        except requests.exceptions.RequestException:
            raise exceptions.ConnectionError
        import hashlib
        h = hashlib.md5(r.content).hexdigest()
        cursor = db.cursor()
        cursor.execute("SELECT Code FROM Captcha WHERE Hash=?", (h,))
        res = cursor.fetchall()
        try:
            return res[0][0]
        except IndexError:
            return
