"""Shared errors without platform credentials or raw API responses."""

class DownloadError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
