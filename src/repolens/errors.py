class RepoLensError(Exception):
    """A safe, actionable failure that can be shown in the local UI."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
