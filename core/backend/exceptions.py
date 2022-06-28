class JudgeException(Exception):
    pass


class ConnectionError(JudgeException):
    pass


class LoginError(JudgeException):
    pass


class UserNotExist(LoginError):
    pass


class PasswordError(LoginError):
    pass


class LoginRequired(JudgeException):
    pass


class SubmitError(JudgeException):
    pass
