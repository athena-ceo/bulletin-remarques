"""Structured logging utilities for the bulletin generation application."""

from __future__ import annotations

import logging
import json
from datetime import datetime
from typing import Optional, Any
from pathlib import Path


class StructuredLogger:
    """Logger that outputs structured JSON logs."""

    def __init__(self, name: str, log_file: Optional[str] = None):
        """Initialize structured logger.

        Args:
            name: Logger name
            log_file: Optional path to log file
        """
        self.logger = logging.getLogger(name)
        self.log_file = log_file

        if log_file:
            handler = logging.FileHandler(log_file)
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)

    def _log_structured(self, level: str, event: str, **kwargs: Any) -> None:
        """Log a structured message.

        Args:
            level: Log level (info, warning, error)
            event: Event name
            **kwargs: Additional fields to log
        """
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "event": event,
            **kwargs,
        }

        log_method = getattr(self.logger, level)
        log_method(json.dumps(log_data))

    def log_evaluation(
        self,
        student_name: str,
        class_type: str,
        duration_ms: float,
        success: bool,
        error: Optional[str] = None,
    ) -> None:
        """Log an evaluation generation event.

        Args:
            student_name: Name of the student
            class_type: Type of class (ECG2 or KE4)
            duration_ms: Duration in milliseconds
            success: Whether generation succeeded
            error: Error message if failed
        """
        self._log_structured(
            "info",
            "evaluation_generated",
            student=student_name,
            class_type=class_type,
            duration_ms=duration_ms,
            success=success,
            error=error,
        )

    def log_file_validation(
        self,
        file_path: str,
        is_valid: bool,
        sheets_found: list[str],
        error: Optional[str] = None,
    ) -> None:
        """Log a file validation event.

        Args:
            file_path: Path to the Excel file
            is_valid: Whether validation succeeded
            sheets_found: List of valid sheets found
            error: Error message if validation failed
        """
        self._log_structured(
            "info",
            "file_validated",
            file=str(Path(file_path).name),
            is_valid=is_valid,
            sheets_found=sheets_found,
            error=error,
        )

    def log_session_summary(
        self,
        total_students: int,
        successful: int,
        failed: int,
        total_duration_ms: float,
    ) -> None:
        """Log a session summary.

        Args:
            total_students: Total number of students processed
            successful: Number of successful evaluations
            failed: Number of failed evaluations
            total_duration_ms: Total duration in milliseconds
        """
        self._log_structured(
            "info",
            "session_completed",
            total_students=total_students,
            successful=successful,
            failed=failed,
            total_duration_ms=total_duration_ms,
            avg_duration_ms=(
                total_duration_ms / total_students if total_students > 0 else 0
            ),
        )
