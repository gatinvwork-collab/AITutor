class AppError(Exception):
    """An intentionally public, secret-free error."""

    def __init__(self, message, code="validation"):
        super().__init__(message)
        self.code = code


def require(condition, message, code="validation"):
    if not condition:
        raise AppError(message, code)
