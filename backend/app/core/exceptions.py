"""Custom exception hierarchy for the application."""


class AppBaseException(Exception):
    """Base exception for all application errors."""

    def __init__(self, message: str, detail: str | None = None):
        self.message = message
        self.detail = detail
        super().__init__(message)


class PDFParseError(AppBaseException):
    """Raised when PDF parsing fails."""
    pass


class PDFImportError(AppBaseException):
    """Raised when PDF import process fails."""
    pass


class QuestionNotFoundError(AppBaseException):
    """Raised when a question is not found in the database."""
    pass


class QuizError(AppBaseException):
    """Raised when quiz operations fail."""
    pass
