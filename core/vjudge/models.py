from datetime import datetime, timezone
from sqlalchemy import Column, Integer, Boolean, String, DateTime, UniqueConstraint

from . import db


class Submission(db.Model):
    __tablename__ = 'submissions'
    id = Column(Integer, primary_key=True)
    user_id = Column(String, index=True)
    oj_name = Column(String, nullable=False)
    problem_id = Column(String, nullable=False)
    language = Column(String, nullable=False)
    source_code = Column(String, nullable=False)
    run_id = Column(String)
    verdict = Column(String, default='Queuing')
    exe_time = Column(Integer)
    exe_mem = Column(Integer)
    time_stamp = Column(DateTime, default=datetime.utcnow)

    def to_json(self):
        submission_json = {
            'id': self.id,
            'oj_name': self.oj_name,
            'problem_id': self.problem_id,
            'verdict': self.verdict,
            'exe_time': self.exe_time,
            'exe_mem': self.exe_mem
        }
        return submission_json

    def __repr__(self):
        return (f'<Submission(id={self.id}, user_id={self.user_id}, oj_name={self.oj_name}, '
                f'problem_id={self.problem_id} verdict="{self.verdict}")>')


class Problem(db.Model):
    __tablename__ = 'problems'
    oj_name = Column(String, primary_key=True, index=True)
    problem_id = Column(String, primary_key=True, index=True)
    last_update = Column(DateTime, nullable=False)
    title = Column(String)
    description = Column(String)
    input = Column(String)
    output = Column(String)
    sample_input = Column(String)
    sample_output = Column(String)
    time_limit = Column(Integer)
    mem_limit = Column(Integer)

    def to_json(self):
        problem_json = {
            'oj_name': self.oj_name,
            'problem_id': self.problem_id,
            'last_update': self._to_timestamp(self.last_update),
            'title': self.title,
            'description': self.description,
            'input': self.input,
            'output': self.output,
            'sample_input': self.sample_input,
            'sample_output': self.sample_output,
            'time_limit': self.time_limit,
            'mem_limit': self.mem_limit
        }
        return problem_json

    def summary(self):
        summary_json = {
            'oj_name': self.oj_name,
            'problem_id': self.problem_id,
            'title': self.title,
        }
        return summary_json

    @staticmethod
    def _to_timestamp(dt):
        dt = datetime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, tzinfo=timezone.utc)
        return dt.timestamp()

    def __repr__(self):
        return f'<Problem(oj_name={self.oj_name}, problem_id={self.problem_id}, title={self.title})>'


class Contest(db.Model):
    __tablename__ = 'contests'
    oj_name = Column(String, primary_key=True)
    site = Column(String, nullable=False)
    contest_id = Column(String, nullable=False)
    title = Column(String, default='')
    public = Column(Boolean, default=False)
    status = Column(String, default='Pending')
    start_time = Column(DateTime, default=datetime.utcfromtimestamp(0))
    end_time = Column(DateTime, default=datetime.utcfromtimestamp(0))

    __table_args__ = (UniqueConstraint('site', 'contest_id', name='_site_contest_id_uc'),)

    def to_json(self):
        contest_json = {
            'oj_name': self.oj_name,
            'site': self.site,
            'contest_id': self.contest_id,
            'title': self.title,
            'public': self.public,
            'status': self.status,
            'start_time': self._to_timestamp(self.start_time),
            'end_time': self._to_timestamp(self.end_time),
        }
        return contest_json

    @staticmethod
    def _to_timestamp(dt):
        dt = datetime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, tzinfo=timezone.utc)
        return dt.timestamp()

    def __repr__(self):
        return (f'<Contest(site={self.site} contest_id={self.contest_id}, title="{self.title}", '
                f'public={self.public}, status={self.status})>')
