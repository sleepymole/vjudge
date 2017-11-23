class VJudgeException(Exception):
    pass


class ConnectionError(VJudgeException):
    pass


class LoginError(VJudgeException):
    pass


class UserNotExist(LoginError):
    pass


class PasswordError(LoginError):
    pass


class LoginExpired(VJudgeException):
    pass


class LoginRequired(VJudgeException):
    pass


class ProblemNotFound(VJudgeException):
    pass


class LanguageError(VJudgeException):
    pass


class SubmitError(VJudgeException):
    pass
