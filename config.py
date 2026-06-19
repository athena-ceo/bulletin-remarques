"""Configuration constants for the bulletin generation application."""

from __future__ import annotations
from typing import List
from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    """General application configuration."""

    # OpenAI settings
    DEFAULT_MODEL: str = "gpt-5-mini"
    AVAILABLE_MODELS: List[str] = ("gpt-5-mini", "gpt-5")
    DEFAULT_TEMPERATURE: float = 0.7
    MIN_TEMPERATURE: float = 0.0
    MAX_TEMPERATURE: float = 1.0
    TEMPERATURE_STEP: float = 0.1

    # Evaluation constraints
    MAX_REMARK_LENGTH: int = 200

    # Grade thresholds (out of 20)
    WEAK_GRADE_THRESHOLD: float = 9.0
    SOLID_GRADE_THRESHOLD: float = 12.0

    # Test mode defaults
    DEFAULT_TEST_LIMIT: int = 5

    # File output settings
    OUTPUT_FILE_PATTERN: str = "remarques_{class_name}.txt"

    # Logging
    DEFAULT_LOG_LEVEL: str = "INFO"
    VALID_LOG_LEVELS: List[str] = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


# Singleton instance
APP_CONFIG = AppConfig()
