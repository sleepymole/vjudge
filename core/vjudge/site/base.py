import logging
from abc import abstractmethod, ABC

import requests

from config import get_header

logging.basicConfig(level=logging.INFO)


class BaseClient(ABC):
    def __init__(self):
        self._session = requests.session()
        self._session.headers.update(get_header())

    @abstractmethod
    def get_name(self):
        pass

    @abstractmethod
    def get_user_id(self):
        pass

    @abstractmethod
    def get_client_type(self):
        pass

    @abstractmethod
    def login(self, username, password):
        pass

    @abstractmethod
    def check_login(self):
        pass

    @abstractmethod
    def update_cookies(self):
        pass

    @abstractmethod
    def get_problem(self, problem_id):
        pass

    @abstractmethod
    def get_problem_list(self):
        pass

    @abstractmethod
    def submit_problem(self, problem_id, language, source_code):
        pass

    @abstractmethod
    def get_submit_status(self, run_id, **kwargs):
        pass


class ContestInfo(object):
    def __init__(self, site, contest_id, title='', public=True, status='Pending',
                 start_time=0, end_time=0, problem_list=None):
        self.site = site
        self.contest_id = contest_id
        self.title = title
        self.public = public
        self.status = status
        self.start_time = start_time
        self.end_time = end_time
        self.problem_list = problem_list or []

    def to_json(self):
        contest_json = {
            'site': self.site,
            'contest_id': self.contest_id,
            'title': self.title,
            'public': self.public,
            'status': self.status,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'problem_list': self.problem_list
        }
        return contest_json

    def __repr__(self):
        return (f'<ContestInfo(site={self.site} contest_id={self.contest_id}, title="{self.title}", '
                f'public={self.public}, status={self.status})>')


class ContestClient(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def get_contest_id(self):
        pass

    @abstractmethod
    def get_contest_info(self):
        pass

    @abstractmethod
    def refresh_contest_info(self):
        pass

    @classmethod
    @abstractmethod
    def get_recent_contest(cls):
        pass
