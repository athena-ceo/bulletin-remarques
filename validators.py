"""Validation functions for Excel files and student data."""

from __future__ import annotations

from typing import Tuple, Set, List
import pandas as pd
import logging

from config import EXCEL_CONFIG


def get_required_columns(class_type: str) -> Set[str]:
    """Get the required column names for a specific class type.
    
    Args:
        class_type: Type of class ("ECG2" or "KE4")
        
    Returns:
        Set of required column names
    """
    if class_type == "ECG2":
        return set([
            *EXCEL_CONFIG.ECG2_COMPREHENSION_COLS,
            *EXCEL_CONFIG.ECG2_ESSAI_COLS,
            *EXCEL_CONFIG.ECG2_TRADUCTION_COLS,
            *EXCEL_CONFIG.ECG2_MOYENNE_COLS,
        ])
    else:  # KE4
        return set([
            *EXCEL_CONFIG.KE4_SYNTHESE_COLS,
            *EXCEL_CONFIG.KE4_ESSAI_COLS,
            *EXCEL_CONFIG.KE4_TRADUCTION_COLS,
            *EXCEL_CONFIG.KE4_MOYENNE_COLS,
        ])


def validate_excel_structure(df: pd.DataFrame, class_type: str) -> Tuple[bool, str]:
    """Validate Excel file structure for a specific class type.
    
    Args:
        df: DataFrame to validate
        class_type: Type of class ("ECG2" or "KE4")
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check if DataFrame is empty
    if len(df) == 0:
        return False, f"Le fichier pour {class_type} est vide (aucune ligne de données)"
    
    # Check if DataFrame has at least 3 columns (for student info)
    if len(df.columns) < 3:
        return False, f"Structure invalide: moins de 3 colonnes trouvées dans {class_type}"
    
    # Get required columns
    required_cols = get_required_columns(class_type)
    existing_cols = set(df.columns)
    
    # Check for missing columns
    missing_cols = required_cols - existing_cols
    if missing_cols:
        return False, f"Colonnes manquantes dans {class_type}: {', '.join(sorted(missing_cols))}"
    
    # Check if there's at least one valid student row
    valid_rows = df.iloc[:, 1].notna() & df.iloc[:, 2].notna()
    if not valid_rows.any():
        return False, f"Aucun élève valide trouvé dans {class_type} (nom et prénom manquants)"
    
    logging.info(f"Validation réussie pour {class_type}: {valid_rows.sum()} élèves valides trouvés")
    return True, "OK"


def validate_excel_file(excel_path: str) -> Tuple[bool, str, List[str]]:
    """Validate an Excel file for bulletin generation.
    
    Args:
        excel_path: Path to the Excel file
        
    Returns:
        Tuple of (is_valid, error_message, valid_sheets)
    """
    try:
        xl = pd.ExcelFile(excel_path)
    except Exception as e:
        return False, f"Erreur lors de la lecture du fichier Excel: {e}", []
    
    # Check if file has at least one valid sheet
    valid_sheets = [sheet for sheet in EXCEL_CONFIG.VALID_SHEET_NAMES if sheet in xl.sheet_names]
    
    if not valid_sheets:
        return False, f"Aucun onglet valide trouvé. Onglets requis: {', '.join(EXCEL_CONFIG.VALID_SHEET_NAMES)}", []
    
    # Validate structure of each sheet
    for sheet_name in valid_sheets:
        df = pd.read_excel(excel_path, sheet_name=sheet_name)
        is_valid, error_msg = validate_excel_structure(df, sheet_name)
        if not is_valid:
            return False, error_msg, []
    
    return True, "OK", valid_sheets

