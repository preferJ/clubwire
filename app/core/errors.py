"""도메인 예외. 서비스 계층은 HTTP를 모르고 이 예외만 던진다."""


class DomainError(Exception):
    status_code = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class BadRequest(DomainError):
    status_code = 400
    code = "BAD_REQUEST"


class Unauthorized(DomainError):
    status_code = 401
    code = "UNAUTHORIZED"


class Forbidden(DomainError):
    status_code = 403
    code = "FORBIDDEN"


class NotFound(DomainError):
    status_code = 404
    code = "NOT_FOUND"


class Conflict(DomainError):
    status_code = 409
    code = "CONFLICT"


class TooManyRequests(DomainError):
    status_code = 429
    code = "TOO_MANY_REQUESTS"
