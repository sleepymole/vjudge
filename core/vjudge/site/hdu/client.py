import re
from abc import abstractmethod
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from bs4.element import NavigableString

from .. import exceptions
from ..base import BaseClient, ContestClient, ContestInfo

__all__ = ('HDUClient', 'HDUContestClient')

BASE_URL = 'http://acm.hdu.edu.cn'

LANG_ID = {'G++': '0', 'GCC': '1', 'C++': '2',
           'C': '3', 'Pascal': '4', 'Java': '5', 'C#': '6'}

PAGE_TITLES = {'Problem Description': 'description', 'Input': 'input', 'Output': 'output',
               'Sample Input': 'sample_input', 'Sample Output': 'sample_output'}


class _UniClient(BaseClient):
    def __init__(self, auth=None, client_type='practice', contest_id='0', timeout=5):
        super().__init__()
        self.auth = auth
        self.client_type = client_type
        self.contest_id = contest_id
        self.timeout = timeout
        if auth is not None:
            self.username, self.password = auth
            self.login(self.username, self.password)

    @abstractmethod
    def get_name(self):
        pass

    def get_user_id(self):
        if self.auth is None:
            raise exceptions.LoginRequired('Login is required')
        return self.username

    def get_client_type(self):
        return self.client_type

    def login(self, username, password):
        url = self._get_login_url()
        data = {
            'login': 'Sign in',
            'username': username,
            'userpass': password
        }
        try:
            self._request_url('post', url, data=data)
        except exceptions.LoginRequired:
            raise exceptions.LoginError('User not exist or wrong password')
        self.auth = (username, password)
        self.username = username
        self.password = password

    @abstractmethod
    def check_login(self):
        pass

    def update_cookies(self):
        if self.auth is None:
            raise exceptions.LoginRequired('Login is required')
        self.login(self.username, self.password)

    def get_problem(self, problem_id):
        url = self._get_problem_url(problem_id)
        resp = self._request_url('get', url)
        return self._parse_problem(resp)

    @abstractmethod
    def get_problem_list(self):
        pass

    def submit_problem(self, problem_id, language, source_code):
        if self.auth is None:
            raise exceptions.LoginRequired('Login is required')
        if language not in LANG_ID:
            raise exceptions.SubmitError(f'Language "{language}" is not supported')
        if self.client_type == 'contest':
            source_code = self.__class__._encode_source_code(source_code)
        data = {
            'problemid': problem_id,
            'language': LANG_ID[language],
            'usercode': source_code
        }
        if self.client_type == 'contest':
            data['submit'] = 'Submit'
        else:
            data['check'] = '0'
        url = self._get_submit_url()
        resp = self._request_url('post', url, data=data)
        if re.search('Code length is improper', resp):
            raise exceptions.SubmitError('Code length is too short')
        if re.search("Please don't re-submit in 5 seconds, thank you.", resp):
            raise exceptions.SubmitError('Submit too frequently')
        if not re.search('Realtime Status', resp):
            raise exceptions.SubmitError('Submit failed unexpectedly')
        url = self._get_status_url(problem_id=problem_id, user_id=self.username)
        resp = self._request_url('get', url)
        try:
            tables = BeautifulSoup(resp, 'lxml').find_all('table')
            tables.reverse()
            pattern = re.compile(r'Run ID.*Judge Status.*Author', re.DOTALL)
            table = next(filter(lambda x: re.search(pattern, str(x)), tables))
            tag = table.find('tr', align="center")
            run_id = tag.find('td').text.strip()
        except (AttributeError, StopIteration):
            raise exceptions.SubmitError('Submit failed unexpectedly')
        return run_id

    def get_submit_status(self, run_id, **kwargs):
        user_id = kwargs.get('user_id', '')
        problem_id = kwargs.get('problem_id', '')
        url = self._get_status_url(run_id=run_id, problem_id=problem_id, user_id=user_id)
        resp = self._request_url('get', url)
        result = self.__class__._find_verdict(resp, run_id)
        if result is not None:
            return result
        if self.client_type == 'contest':
            for page in range(2, 5):
                status_url = url + f'&page={page}'
                resp = self._request_url('get', status_url)
                result = self.__class__._find_verdict(resp, run_id)
                if result is not None:
                    return result

    def _request_url(self, method, url, data=None, timeout=None):
        if timeout is None:
            timeout = self.timeout
        try:
            r = self._session.request(method, url, data=data, timeout=timeout)
        except requests.exceptions.RequestException:
            raise exceptions.ConnectionError(f'Request "{url}" failed')
        if re.search('Sign In Your Account', r.text):
            raise exceptions.LoginRequired('Login is required')
        return r.text

    def _get_login_url(self):
        login_url = f'{BASE_URL}/userloginex.php?action=login'
        if self.client_type == 'contest':
            login_url += f'&cid={self.contest_id}&notice=0'
        return login_url

    def _get_submit_url(self):
        if self.client_type == 'contest':
            return f'{BASE_URL}/contests/contest_submit.php?action=submit&cid={self.contest_id}'
        else:
            return f'{BASE_URL}/submit.php?action=submit'

    def _get_status_url(self, run_id='', problem_id='', user_id=''):
        if self.client_type == 'contest':
            return (f'{BASE_URL}/contests/contest_status.php?'
                    f'cid={self.contest_id}&pid={problem_id}&user={user_id}&lang=0&status=0')
        else:
            return f'{BASE_URL}/status.php?first={run_id}&pid={problem_id}&user={user_id}&lang=0&status=0'

    def _get_problem_url(self, problem_id):
        if self.client_type == 'contest':
            return f'{BASE_URL}/contests/contest_showproblem.php?pid={problem_id}&cid={self.contest_id}'
        else:
            return f'{BASE_URL}/showproblem.php?pid={problem_id}'

    def _parse_problem(self, text):
        result = {}
        pattern = re.compile((r'Time Limit:.*?[0-9]*/([0-9]*).*?MS.*?\(Java/Others\).*?'
                              'Memory Limit:.*?[0-9]*/([0-9]*).*?K.*?\(Java/Others\)'))
        # find time limit and mem limit
        limit = re.search(pattern, text)
        if limit:
            result['time_limit'] = limit.group(1)
            result['mem_limit'] = limit.group(2)
        soup = BeautifulSoup(text, 'lxml')
        # replace relative url
        img_tags = soup.find_all('img')
        for tag in img_tags:
            if hasattr(tag, 'src'):
                img_url = urljoin(self._get_problem_url(''), tag['src'])
                tag['src'] = img_url
        if soup.h1:
            result['title'] = soup.h1.text
            if result['title'] == 'System Message':
                return
        tags = soup.find_all('div', 'panel_title', align='left')
        for t in tags:
            title = t.string
            if title in PAGE_TITLES:
                tag = t.next_sibling
                limit = 0
                while tag and type(tag) is NavigableString and limit < 3:
                    tag = tag.next_sibling
                    limit += 1
                if tag is None or type(tag) is NavigableString:
                    continue
                res = re.match('<div.*?>(.*)</div>$', str(tag), re.DOTALL)
                if res:
                    result[PAGE_TITLES[title]] = res.group(1)
        return result

    @staticmethod
    def _find_verdict(text, run_id):
        soup = BeautifulSoup(text, 'lxml')
        tables = soup.find_all('table')
        tables.reverse()
        try:
            pattern = re.compile(r'Run ID.*Judge Status.*Author', re.DOTALL)
            table = next(filter(lambda x: re.search(pattern, str(x)), tables))
        except StopIteration:
            return
        tags = table.find_all('tr', align="center")
        for tag in tags:
            result = [x.text.strip() for x in tag.find_all('td')]
            if len(result) < 6:
                continue
            if result[0] == run_id:
                verdict = result[2]
                try:
                    exe_time = int(result[4].replace('MS', ''))
                    exe_mem = int(result[5].replace('K', ''))
                except ValueError:
                    continue
                if re.search('Runtime Error', verdict):
                    verdict = 'Runtime Error'
                return verdict, exe_time, exe_mem

    @staticmethod
    def _encode_source_code(code):
        from urllib import parse
        import base64
        return base64.b64encode(parse.quote(code).encode('utf-8')).decode('utf-8')


class HDUClient(_UniClient):
    def __init__(self, auth=None, **kwargs):
        super().__init__(auth, **kwargs)
        self.name = 'hdu'

    def get_name(self):
        return self.name

    def check_login(self):
        url = BASE_URL + '/control_panel.php'
        try:
            self._request_url('get', url)
        except exceptions.LoginRequired:
            return False
        return True

    def get_problem_list(self):
        url = f'{BASE_URL}/listproblem.php'
        resp = self._request_url('get', url)
        vols = set(re.findall(r'listproblem.php\?vol=([0-9]+)', resp))
        vols = [int(x) for x in vols]
        vols.sort()
        result = []
        for vol in vols:
            ex_url = url + f'?vol={vol}'
            vol += 1
            try:
                resp = self._request_url('get', ex_url)
            except exceptions.ConnectionError:
                break
            ids = self.__class__._parse_problem_id(resp)
            result += ids
        result.sort()
        return result

    @staticmethod
    def _parse_problem_id(text):
        pattern = re.compile(r'p\([^,()]+?,([^,()]+?)(,[^,()]+?){4}\);', re.DOTALL)
        res = re.findall(pattern, text)
        return [x[0] for x in res]


class HDUContestClient(_UniClient, ContestClient):
    def __init__(self, auth=None, contest_id=None, **kwargs):
        timeout = kwargs.get('timeout', 5)
        if contest_id is None:
            raise exceptions.JudgeException('You must specific a contest id')
        super().__init__(auth, 'contest', str(contest_id), timeout)
        self.name = f'hdu_ct_{contest_id}'
        self._contest_info = ContestInfo('hdu', self.contest_id)
        self.refresh_contest_info()

    def get_name(self):
        return self.name

    def get_contest_id(self):
        return self.contest_id

    def check_login(self):
        raise NotImplementedError

    def get_contest_info(self):
        return self._contest_info

    def get_problem_list(self):
        return self._contest_info.problem_list

    def get_problem(self, problem_id):
        if not self._contest_info.public and self.auth is None:
            raise exceptions.LoginRequired('Login is required')
        return super().get_problem(problem_id)

    def submit_problem(self, problem_id, language, source_code):
        self.refresh_contest_info()
        if self._contest_info.status == 'Pending':
            raise exceptions.SubmitError('Contest has not begun')
        if self._contest_info.status == 'Ended':
            raise exceptions.SubmitError('Contest is ended')
        return super().submit_problem(problem_id, language, source_code)

    def get_submit_status(self, run_id, **kwargs):
        if not self._contest_info.public and self.auth is None:
            raise exceptions.LoginRequired('Login is required')
        return super().get_submit_status(run_id, **kwargs)

    def refresh_contest_info(self):
        url = f'{BASE_URL}/contests/contest_show.php?cid={self.contest_id}'
        resp = self._request_url('get', url)
        if re.search(r'System Message', resp):
            raise exceptions.ConnectionError(f'Contest {self.contest_id} not exists')
        self._contest_info.problem_list = self.__class__._parse_problem_id(resp)
        soup = BeautifulSoup(resp, 'lxml')
        h1 = self._contest_info.title = soup.h1
        if h1:
            self._contest_info.title = h1.get_text()
        divs = soup.find_all('div')
        divs.reverse()
        try:
            pattern = re.compile(r'Start.*Time.*Contest.*Type.*Contest.*Status', re.DOTALL)
            div = next(filter(lambda x: re.search(pattern, str(x)), divs))
        except StopIteration:
            return
        pattern = re.compile(
            r'Start *?Time *?: *?([0-9]{4})-([0-9]{2})-([0-9]{2}) *?([0-9]{2}):([0-9]{2}):([0-9]{2}).*?'
            r'End *?Time *?: *?([0-9]{4})-([0-9]{2})-([0-9]{2}) *?([0-9]{2}):([0-9]{2}):([0-9]{2}).*?'
            r'Contest *?Type *?:(.*?)Contest *?Status.*?:(.*?)Current.*?Server.*?Time',
            re.DOTALL)
        res = re.search(pattern, div.get_text())
        if res:
            res = [x.strip() for x in res.groups()]
            self._contest_info.start_time = self._to_timestamp(res[0:6])
            self._contest_info.end_time = self._to_timestamp(res[6:12])
            self._contest_info.public = res[12] == 'Public'
            self._contest_info.status = res[13]

    @classmethod
    def get_recent_contest(cls):
        from ..base import get_header
        session = requests.session()
        session.headers.update(get_header())
        url = f'{BASE_URL}/contests/contest_list.php'
        try:
            r = session.get(url, timeout=5)
        except requests.exceptions.RequestException:
            return []
        soup = BeautifulSoup(r.text, 'lxml')
        table = soup.find('table', 'table_text')
        if table is None:
            return []
        tags = table.find_all('tr', align='center')
        result = []
        for tag in tags:
            tds = tag.find_all('td')
            tds = [x.text.strip() for x in tds]
            if len(tds) < 6:
                continue
            contest_info = ContestInfo('hdu', contest_id=tds[0], title=tds[1], status=tds[4])
            r = re.search('([0-9]{4})-([0-9]{2})-([0-9]{2}) *?([0-9]{2}):([0-9]{2}):([0-9]{2})', tds[2])
            if r:
                contest_info.start_time = cls._to_timestamp(r.groups())
            if tds[3] != 'Public':
                contest_info.public = False
            result.append(contest_info)
        return result

    @staticmethod
    def _parse_problem_id(text):
        res = []
        soup = BeautifulSoup(text, 'lxml')
        tables = soup.find_all('table')
        try:
            pattern = re.compile(r'Solved.*Title.*Ratio', re.DOTALL)
            table = next(filter(lambda x: re.search(pattern, str(x)), tables))
        except StopIteration:
            return res
        tags = table.find_all('tr', align="center")
        for tag in tags:
            tds = [x.text for x in tag.find_all('td')]
            if len(tds) >= 2:
                res.append(tds[1])
        return res

    @staticmethod
    def _to_timestamp(d):
        try:
            d = [int(x) for x in d]
        except ValueError:
            return 0

        utc = datetime(*d, tzinfo=timezone.utc) - timedelta(hours=8)
        return utc.timestamp()
