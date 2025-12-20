"""Custom exceptions for the bulletin generation application."""

from __future__ import annotations


class BulletinError(Exception):
    """Base exception for all bulletin generation errors."""

    pass


class ExcelFileError(BulletinError):
    """Exception raised for Excel file related errors."""

    pass


class ExcelValidationError(ExcelFileError):
    """Exception raised when Excel file structure is invalid."""

    pass


class StudentDataError(BulletinError):
    """Exception raised for errors extracting student data."""

    pass


class EvaluationGenerationError(BulletinError):
    """Exception raised when AI evaluation generation fails."""

    pass


class APIError(BulletinError):
    """Exception raised for OpenAI API errors."""

    pass
