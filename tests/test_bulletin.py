"""Unit tests for the bulletin generation application."""

from __future__ import annotations

import pytest
import pandas as pd

from column_mapping import (
    AssessmentBlockMapping,
    SheetColumnMapping,
    auto_detect_column_mapping,
    compute_block_moyenne,
    mapping_is_complete,
)
from generate_evaluations import (
    calculate_general_average,
    extract_student_data,
    format_student_data_for_prompt,
)
from validators import validate_excel_structure


def _legacy_ecg2_mapping(class_name: str = "ECG2") -> SheetColumnMapping:
    """Build the legacy three-CB mapping used in older spreadsheets."""
    blocks = []
    essai_cols = ["Essai", "Essai.1", "Essai.2"]
    trad_cols = ["Traduction", "Traduction.1", "Traduction.2"]
    moy_cols = ["Moyenne CB1", "Moyenne CB2", "Moyenne CB3"]
    main_cols = ["CB1 Compréhension", "CB2 Compréhension", "CB3 Compréhension"]

    for index in range(3):
        blocks.append(
            AssessmentBlockMapping(
                label=f"CB{index + 1}",
                main_exercise_col=main_cols[index],
                main_exercise_type="comprehension",
                essai_col=essai_cols[index],
                traduction_col=trad_cols[index],
                moyenne_col=moy_cols[index],
            )
        )
    return SheetColumnMapping(class_name=class_name, blocks=blocks)


def _legacy_ke4_mapping(class_name: str = "KE4") -> SheetColumnMapping:
    """Build the legacy three-CB synthèse mapping."""
    blocks = []
    essai_cols = ["Essai", "Essai.1", "Essai.2"]
    trad_cols = ["Traduction", "Traduction.1", "Traduction.2"]
    moy_cols = ["Moyenne CB1", "Moyenne CB2", "Moyenne CB3"]
    main_cols = ["CB1 Synthèse", "CB2 Synthèse", "CB3 Synthèse"]

    for index in range(3):
        blocks.append(
            AssessmentBlockMapping(
                label=f"CB{index + 1}",
                main_exercise_col=main_cols[index],
                main_exercise_type="synthese",
                essai_col=essai_cols[index],
                traduction_col=trad_cols[index],
                moyenne_col=moy_cols[index],
            )
        )
    return SheetColumnMapping(class_name=class_name, blocks=blocks)


class TestCalculateGeneralAverage:
    """Tests for calculate_general_average function."""

    def test_all_grades_present(self):
        result = calculate_general_average(10.0, 12.0, 14.0)
        assert result == 12.0

    def test_one_grade_missing(self):
        result = calculate_general_average(None, 12.0, 14.0)
        assert result == 13.0

    def test_all_grades_missing(self):
        result = calculate_general_average(None, None, None)
        assert result is None


class TestComputeBlockMoyenne:
    """Tests for compute_block_moyenne function."""

    def test_computes_from_three_grades(self):
        result = compute_block_moyenne(10.0, 12.0, 14.0)
        assert result == 12.0

    def test_computes_from_two_grades(self):
        result = compute_block_moyenne(10.0, None, 14.0)
        assert result == 12.0

    def test_returns_none_when_empty(self):
        result = compute_block_moyenne(None, None, None)
        assert result is None


class TestAutoDetectColumnMapping:
    """Tests for auto_detect_column_mapping function."""

    def test_detects_legacy_ecg2_layout(self):
        df = pd.DataFrame(
            {
                0: [1],
                1: ["Dupont"],
                2: ["Marie"],
                "CB1 Compréhension": [12.5],
                "Essai": [14.0],
                "Traduction": [11.0],
                "Moyenne CB1": [12.5],
                "CB2 Compréhension": [13.0],
                "Essai.1": [15.0],
                "Traduction.1": [12.0],
                "Moyenne CB2": [13.3],
            }
        )

        mapping = auto_detect_column_mapping(df, "ECG2")

        assert len(mapping.blocks) == 2
        assert mapping.blocks[0].label == "CB1"
        assert mapping.blocks[0].main_exercise_type == "comprehension"
        assert mapping.blocks[1].essai_col == "Essai.1"

    def test_detects_dst_blocks(self):
        df = pd.DataFrame(
            {
                0: [1],
                1: ["Martin"],
                2: ["Jean"],
                "DST1 Synthèse": [11.0],
                "DST1 Essai": [12.0],
                "DST1 Traduction": [10.0],
                "Moyenne DST1": [11.0],
                "DST2 Synthèse": [13.0],
                "DST2 Essai": [14.0],
                "DST2 Traduction": [12.0],
            }
        )

        mapping = auto_detect_column_mapping(df, "3G1")

        assert mapping.class_name == "3G1"
        assert len(mapping.blocks) == 2
        assert mapping.blocks[0].label == "DST1"
        assert mapping.blocks[0].main_exercise_type == "synthese"
        assert mapping.blocks[1].moyenne_col is None


class TestExtractStudentData:
    """Tests for extract_student_data function."""

    def test_valid_ecg2_student(self):
        row = pd.Series(
            {
                0: 1,
                1: "Dupont",
                2: "Marie",
                "CB1 Compréhension": 12.5,
                "Essai": 14.0,
                "Traduction": 11.0,
                "Moyenne CB1": 12.5,
                "CB2 Compréhension": 13.0,
                "Essai.1": 15.0,
                "Traduction.1": 12.0,
                "Moyenne CB2": 13.3,
                "CB3 Compréhension": 14.0,
                "Essai.2": 16.0,
                "Traduction.2": 13.0,
                "Moyenne CB3": 14.3,
            }
        )

        result = extract_student_data(row, _legacy_ecg2_mapping())

        assert result is not None
        assert result["nom"] == "Dupont"
        assert result["class_name"] == "ECG2"
        assert result["assessments"][0]["main"] == 12.5
        assert result["assessments"][0]["main_type"] == "comprehension"

    def test_valid_ke4_student(self):
        row = pd.Series(
            {
                0: 1,
                1: "Martin",
                2: "Jean",
                "CB1 Synthèse": 12.5,
                "Essai": 14.0,
                "Traduction": 11.0,
                "Moyenne CB1": 12.5,
                "CB2 Synthèse": 13.0,
                "Essai.1": 15.0,
                "Traduction.1": 12.0,
                "Moyenne CB2": 13.3,
                "CB3 Synthèse": 14.0,
                "Essai.2": 16.0,
                "Traduction.2": 13.0,
                "Moyenne CB3": 14.3,
            }
        )

        result = extract_student_data(row, _legacy_ke4_mapping())

        assert result is not None
        assert result["assessments"][0]["main_type"] == "synthese"

    def test_computes_missing_moyenne(self):
        mapping = SheetColumnMapping(
            class_name="ECG2",
            blocks=[
                AssessmentBlockMapping(
                    label="CB1",
                    main_exercise_col="CB1 Compréhension",
                    main_exercise_type="comprehension",
                    essai_col="Essai",
                    traduction_col="Traduction",
                    moyenne_col=None,
                )
            ],
        )
        row = pd.Series(
            {
                0: 1,
                1: "Dupont",
                2: "Marie",
                "CB1 Compréhension": 10.0,
                "Essai": 12.0,
                "Traduction": 14.0,
            }
        )

        result = extract_student_data(row, mapping)

        assert result is not None
        assert result["assessments"][0]["moyenne"] == 12.0

    def test_mixed_block_types(self):
        mapping = SheetColumnMapping(
            class_name="Mixed",
            blocks=[
                AssessmentBlockMapping(
                    label="CB1",
                    main_exercise_col="CB1 Compréhension",
                    main_exercise_type="comprehension",
                    essai_col="Essai",
                    traduction_col="Traduction",
                    moyenne_col="Moyenne CB1",
                ),
                AssessmentBlockMapping(
                    label="DST2",
                    main_exercise_col="DST2 Synthèse",
                    main_exercise_type="synthese",
                    essai_col="DST2 Essai",
                    traduction_col="DST2 Traduction",
                    moyenne_col=None,
                ),
            ],
        )
        row = pd.Series(
            {
                0: 1,
                1: "Bernard",
                2: "Paul",
                "CB1 Compréhension": 11.0,
                "Essai": 12.0,
                "Traduction": 10.0,
                "Moyenne CB1": 11.0,
                "DST2 Synthèse": 13.0,
                "DST2 Essai": 14.0,
                "DST2 Traduction": 12.0,
            }
        )

        result = extract_student_data(row, mapping)

        assert result is not None
        assert result["assessments"][0]["main_type"] == "comprehension"
        assert result["assessments"][1]["main_type"] == "synthese"
        assert result["assessments"][1]["moyenne"] == 13.0

    def test_moyennes_row_filtered(self):
        row = pd.Series({0: pd.NA, 1: "Moyennes", 2: pd.NA})
        result = extract_student_data(row, _legacy_ecg2_mapping())
        assert result is None


class TestFormatStudentDataForPrompt:
    """Tests for format_student_data_for_prompt function."""

    def test_format_ecg2_student(self):
        student_data = {
            "nom": "Dupont",
            "prenom": "Marie",
            "class_name": "ECG2",
            "assessments": [
                {
                    "label": "CB1",
                    "main_type": "comprehension",
                    "main": 12.5,
                    "essai": 14.0,
                    "traduction": 11.0,
                    "moyenne": 12.5,
                }
            ],
        }

        result = format_student_data_for_prompt(student_data)

        assert "Marie Dupont" in result
        assert "ECG2" in result
        assert "Compréhension" in result
        assert "12.5" in result

    def test_format_with_absent_grades(self):
        student_data = {
            "nom": "Martin",
            "prenom": "Jean",
            "class_name": "ECG2",
            "assessments": [
                {
                    "label": "CB1",
                    "main_type": "comprehension",
                    "main": pd.NA,
                    "essai": 14.0,
                    "traduction": 11.0,
                    "moyenne": 12.5,
                }
            ],
        }

        result = format_student_data_for_prompt(student_data)

        assert "ABS" in result


class TestValidators:
    """Tests for validation functions."""

    def test_validate_valid_ecg2_structure(self):
        df = pd.DataFrame(
            {
                0: [1, 2, 3],
                1: ["Dupont", "Martin", "Bernard"],
                2: ["Marie", "Jean", "Paul"],
                "CB1 Compréhension": [12.5, 13.0, 14.0],
                "Essai": [14.0, 15.0, 16.0],
                "Traduction": [11.0, 12.0, 13.0],
                "Moyenne CB1": [12.5, 13.3, 14.3],
                "CB2 Compréhension": [13.0, 14.0, 15.0],
                "Essai.1": [15.0, 16.0, 17.0],
                "Traduction.1": [12.0, 13.0, 14.0],
                "Moyenne CB2": [13.3, 14.3, 15.3],
                "CB3 Compréhension": [14.0, 15.0, 16.0],
                "Essai.2": [16.0, 17.0, 18.0],
                "Traduction.2": [13.0, 14.0, 15.0],
                "Moyenne CB3": [14.3, 15.3, 16.3],
            }
        )

        is_valid, error_msg = validate_excel_structure(df, _legacy_ecg2_mapping())

        assert is_valid is True
        assert error_msg == "OK"

    def test_validate_empty_dataframe(self):
        df = pd.DataFrame()
        is_valid, error_msg = validate_excel_structure(df, _legacy_ecg2_mapping())
        assert is_valid is False
        assert "vide" in error_msg.lower()

    def test_mapping_is_complete_requires_columns(self):
        mapping = SheetColumnMapping(
            class_name="ECG2",
            blocks=[
                AssessmentBlockMapping(
                    label="CB1",
                    main_exercise_col="",
                    main_exercise_type="comprehension",
                    essai_col="Essai",
                    traduction_col="Traduction",
                    moyenne_col=None,
                )
            ],
        )

        is_complete, message = mapping_is_complete(mapping)

        assert is_complete is False
        assert "principal" in message.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
