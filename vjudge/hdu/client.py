import requests
import re
from bs4 import BeautifulSoup
from ..base import BaseClient
from .. import exceptions

base_url = 'http://acm.hdu.edu.cn'

language_id = {
    'G++': '0',
    'GCC': '1',
    'C++': '2',
    'C': '3',
    'Pascal': '4',
    'Java': '5',
    'C#': '6'
}


class HDUClient(BaseClient):
    def __init__(self, auth=None, **kwargs):
        super().__init__()
        if 'contest_id' in kwargs:
            self.client_type = 'contest'
            self.contest_id = kwargs['contest_id']
        else:
            self.client_type = 'practice'
        self.auth = auth
        self.timeout = kwargs.get('timeout', 5)
        if auth is not None:
            self.username, self.password = auth
            self.login(self.username, self.password)

    def get_login_url(self):
        login_url = base_url + '/userloginex.php?action=login'
        if self.client_type == 'contest': login_url += '&cid={}&notice=0'.format(self.contest_id)
        return login_url

    def get_submit_url(self):
        if self.client_type == 'contest':
            return base_url + '/contests/contest_submit.php?action=submit&cid={}'.format(self.contest_id)
        else:
            return base_url + '/submit.php?action=submit'

    def get_status_url(self, run_id='', problem_id='', user_id=''):
        if self.client_type == 'contest':
            return base_url + '/contests/contest_status.php?cid={}&pid={}&user={}&lang=0&status=0'. \
                format(self.contest_id, problem_id, user_id)
        else:
            return base_url + '/status.php?first={}&pid={}&pid={}&lang=0&status=0'. \
                format(run_id, problem_id, user_id)

    def login(self, username, password):
        url = self.get_login_url()
        data = {
            'login': 'Sign in',
            'username': username,
            'userpass': password
        }
        try:
            r = self._session.post(url, data, timeout=self.timeout)
        except requests.exceptions.RequestException:
            raise exceptions.ConnectionError
        if r.text:
            raise exceptions.LoginError
        self.auth = (username, password)
        self.username = username
        self.password = password

    def check_login(self):
        url = base_url + '/control_panel.php'
        try:
            r = self._session.get(url, timeout=self.timeout)
        except requests.exceptions.RequestException:
            raise exceptions.ConnectionError
        if re.search('Sign In Your Account', r.text):
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
        if language not in language_id:
            raise exceptions.SubmitError
        data = {
            'problemid': problem_id,
            'language': language_id[language],
            'usercode': source_code
        }
        if self.client_type == 'contest':
            data['submit'] = 'Submit'
        else:
            data['check'] = '0'
        url = self.get_submit_url()
        try:
            r = self._session.post(url, data, timeout=self.timeout)
            r.encoding = 'GBK'
            if re.search('Sign In Your Account', r.text):
                raise exceptions.LoginExpired
            if not re.search('Realtime Status', r.text):
                raise exceptions.SubmitError
            status_url = self.get_status_url(problem_id=problem_id, user_id=self.username)
            r = self._session.get(status_url, timeout=self.timeout)
        except requests.exceptions.RequestException:
            raise exceptions.ConnectionError
        try:
            table = BeautifulSoup(r.text, 'lxml').find('div', id='fixed_table').table
            run_id = next(table.find('tr', align="center").stripped_strings)
        except (AttributeError, StopIteration):
            raise exceptions.SubmitError
        return run_id

    def get_submit_status(self, run_id, **kwargs):
        if self.client_type == 'contest':
            raise exceptions.LoginRequired
        user_id = kwargs.get('user_id', '')
        problem_id = kwargs.get('problem_id', '')
        url = self.get_status_url(run_id=run_id, problem_id=problem_id, user_id=user_id)
        try:
            r = self._session.get(url, timeout=self.timeout)
            r.encoding = 'GBK'
        except requests.exceptions.RequestException:
            raise exceptions.ConnectionError
        if re.search('Sign In Your Account', r.text):
            raise exceptions.LoginExpired
        result = self._find_verdict(r.text, run_id)
        if result is not None:
            return result
        if self.client_type == 'contest':
            for page in range(2, 5):
                status_url = url + '&page={}'.format(page)
                try:
                    r = self._session.get(status_url, timeout=self.timeout)
                    r.encoding = 'GBK'
                except requests.exceptions.RequestException:
                    raise exceptions.ConnectionError
                result = self._find_verdict(r.text, run_id)
                if result is not None:
                    return result

    @staticmethod
    def _find_verdict(response, run_id):
        try:
            table = BeautifulSoup(response, 'lxml').find('div', id='fixed_table').table
            tags = table.find_all('tr', align="center")
            for tag in tags:
                result = [x.text for x in tag.find_all('td')]
                if result[0] == run_id:
                    verdict = result[2]
                    exe_time = int(result[4].replace('MS', ''))
                    exe_mem = int(result[5].replace('K', ''))
                    return verdict, exe_time, exe_mem
        except (AttributeError, IndexError, ValueError):
            pass

    @staticmethod
    def _encode_source_code(code):
        from urllib import parse
        import base64
        return base64.b64encode(parse.quote(code).encode('utf-8')).decode('utf-8')
