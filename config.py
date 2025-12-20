"""Configuration constants for the bulletin generation application."""

from __future__ import annotations
from typing import List
from dataclasses import dataclass


@dataclass(frozen=True)
class ExcelColumnConfig:
    """Configuration for Excel file structure."""

    # ECG2 (First year) column names
    ECG2_COMPREHENSION_COLS: List[str] = (
        "CB1 Compréhension",
        "CB2 Compréhension",
        "CB3 Compréhension",
    )
    ECG2_ESSAI_COLS: List[str] = ("Essai", "Essai.1", "Essai.2")
    ECG2_TRADUCTION_COLS: List[str] = ("Traduction", "Traduction.1", "Traduction.2")
    ECG2_MOYENNE_COLS: List[str] = ("Moyenne CB1", "Moyenne CB2", "Moyenne CB3")

    # KE4 (Second year) column names
    KE4_SYNTHESE_COLS: List[str] = ("CB1 Synthèse", "CB2 Synthèse", "CB3 Synthèse")
    KE4_ESSAI_COLS: List[str] = ("Essai", "Essai.1", "Essai.2")
    KE4_TRADUCTION_COLS: List[str] = ("Traduction", "Traduction.1", "Traduction.2")
    KE4_MOYENNE_COLS: List[str] = ("Moyenne CB1", "Moyenne CB2", "Moyenne CB3")

    # Valid sheet names
    VALID_SHEET_NAMES: List[str] = ("ECG2", "KE4")


@dataclass(frozen=True)
class AppConfig:
    """General application configuration."""

    # OpenAI settings
    DEFAULT_MODEL: str = "gpt-5.2"
    AVAILABLE_MODELS: List[str] = ("gpt-5.2", "gpt-4o-mini", "gpt-4o")
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


# Singleton instances
EXCEL_CONFIG = ExcelColumnConfig()
APP_CONFIG = AppConfig()
