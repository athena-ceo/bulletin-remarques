"""Unit tests for the bulletin generation application."""

from __future__ import annotations

import pytest
import pandas as pd
from generate_evaluations import (
    calculate_general_average,
    extract_student_data,
    format_student_data_for_prompt,
)
from validators import validate_excel_structure, get_required_columns


class TestCalculateGeneralAverage:
    """Tests for calculate_general_average function."""
    
    def test_all_grades_present(self):
        """Test with all three grades present."""
        result = calculate_general_average(10.0, 12.0, 14.0)
        assert result == 12.0
    
    def test_one_grade_missing(self):
        """Test with one grade missing."""
        result = calculate_general_average(None, 12.0, 14.0)
        assert result == 13.0
    
    def test_two_grades_missing(self):
        """Test with two grades missing."""
        result = calculate_general_average(15.0, None, None)
        assert result == 15.0
    
    def test_all_grades_missing(self):
        """Test with all grades missing."""
        result = calculate_general_average(None, None, None)
        assert result is None
    
    def test_with_nan_values(self):
        """Test with pandas NaN values."""
        result = calculate_general_average(10.0, pd.NA, 14.0)
        assert result == 12.0


class TestExtractStudentData:
    """Tests for extract_student_data function."""
    
    def test_valid_ecg2_student(self):
        """Test extracting valid ECG2 student data."""
        row = pd.Series({
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
        })
        
        result = extract_student_data(row, "ECG2")
        
        assert result is not None
        assert result["nom"] == "Dupont"
        assert result["prenom"] == "Marie"
        assert result["type"] == "ECG2"
        assert result["cb1"]["comprehension"] == 12.5
        assert result["cb1"]["essai"] == 14.0
    
    def test_invalid_student_missing_name(self):
        """Test with missing student name."""
        row = pd.Series({
            0: 1,
            1: pd.NA,
            2: "Marie",
        })
        
        result = extract_student_data(row, "ECG2")
        assert result is None
    
    def test_valid_ke4_student(self):
        """Test extracting valid KE4 student data."""
        row = pd.Series({
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
        })
        
        result = extract_student_data(row, "KE4")
        
        assert result is not None
        assert result["nom"] == "Martin"
        assert result["prenom"] == "Jean"
        assert result["type"] == "KE4"
        assert result["cb1"]["synthese"] == 12.5


class TestFormatStudentDataForPrompt:
    """Tests for format_student_data_for_prompt function."""
    
    def test_format_ecg2_student(self):
        """Test formatting ECG2 student data."""
        student_data = {
            "nom": "Dupont",
            "prenom": "Marie",
            "type": "ECG2",
            "cb1": {"comprehension": 12.5, "essai": 14.0, "traduction": 11.0, "moyenne": 12.5},
            "cb2": {"comprehension": 13.0, "essai": 15.0, "traduction": 12.0, "moyenne": 13.3},
            "cb3": {"comprehension": 14.0, "essai": 16.0, "traduction": 13.0, "moyenne": 14.3},
        }
        
        result = format_student_data_for_prompt(student_data)
        
        assert "Marie Dupont" in result
        assert "ECG2" in result
        assert "CB1" in result
        assert "Compréhension" in result
        assert "12.5" in result
    
    def test_format_with_absent_grades(self):
        """Test formatting with absent grades."""
        student_data = {
            "nom": "Martin",
            "prenom": "Jean",
            "type": "ECG2",
            "cb1": {"comprehension": pd.NA, "essai": 14.0, "traduction": 11.0, "moyenne": 12.5},
            "cb2": {"comprehension": 13.0, "essai": 15.0, "traduction": 12.0, "moyenne": 13.3},
            "cb3": {"comprehension": 14.0, "essai": 16.0, "traduction": 13.0, "moyenne": 14.3},
        }
        
        result = format_student_data_for_prompt(student_data)
        
        assert "ABS" in result


class TestValidators:
    """Tests for validation functions."""
    
    def test_validate_valid_ecg2_structure(self):
        """Test validating valid ECG2 DataFrame structure."""
        df = pd.DataFrame({
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
        })
        
        is_valid, error_msg = validate_excel_structure(df, "ECG2")
        
        assert is_valid is True
        assert error_msg == "OK"
    
    def test_validate_empty_dataframe(self):
        """Test validating empty DataFrame."""
        df = pd.DataFrame()
        
        is_valid, error_msg = validate_excel_structure(df, "ECG2")
        
        assert is_valid is False
        assert "vide" in error_msg.lower()
    
    def test_validate_missing_columns(self):
        """Test validating DataFrame with missing columns."""
        df = pd.DataFrame({
            0: [1, 2],
            1: ["Dupont", "Martin"],
            2: ["Marie", "Jean"],
            "CB1 Compréhension": [12.5, 13.0],
        })
        
        is_valid, error_msg = validate_excel_structure(df, "ECG2")
        
        assert is_valid is False
        assert "manquantes" in error_msg.lower()
    
    def test_get_required_columns_ecg2(self):
        """Test getting required columns for ECG2."""
        cols = get_required_columns("ECG2")
        
        assert "CB1 Compréhension" in cols
        assert "Essai" in cols
        assert "Traduction" in cols
        assert "Moyenne CB1" in cols
    
    def test_get_required_columns_ke4(self):
        """Test getting required columns for KE4."""
        cols = get_required_columns("KE4")
        
        assert "CB1 Synthèse" in cols
        assert "Essai" in cols
        assert "Traduction" in cols
        assert "Moyenne CB1" in cols


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

