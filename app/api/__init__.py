class ApiError(Exception):
    """A caller-facing error in the single {"error", "message"} shape."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
