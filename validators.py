"""Validation functions for Excel files and student data."""

from __future__ import annotations

from typing import List, Tuple
import pandas as pd
import logging

from column_mapping import SheetColumnMapping, mapping_is_complete


def validate_excel_structure(
    df: pd.DataFrame, mapping: SheetColumnMapping
) -> Tuple[bool, str]:
    """Validate Excel file structure for a mapped worksheet.

    Args:
        df: DataFrame to validate
        mapping: Column mapping for the worksheet

    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(df) == 0:
        return False, f"Le fichier pour {mapping.class_name} est vide (aucune ligne de données)"

    if len(df.columns) < 3:
        return False, (
            f"Structure invalide: moins de 3 colonnes trouvées dans {mapping.class_name}"
        )

    is_complete, completion_msg = mapping_is_complete(mapping)
    if not is_complete:
        return False, completion_msg

    existing_cols = {str(col) for col in df.columns}
    missing_cols = [col for col in mapping.required_columns() if col not in existing_cols]
    if missing_cols:
        return False, (
            f"Colonnes manquantes dans {mapping.class_name}: "
            f"{', '.join(sorted(missing_cols))}"
        )

    valid_rows = (
        df.iloc[:, mapping.last_name_col].notna()
        & df.iloc[:, mapping.first_name_col].notna()
    )
    if not valid_rows.any():
        return False, (
            f"Aucun élève valide trouvé dans {mapping.class_name} "
            f"(nom et prénom manquants)"
        )

    logging.info(
        f"Validation réussie pour {mapping.class_name}: "
        f"{valid_rows.sum()} élèves valides trouvés"
    )
    return True, "OK"


def validate_excel_file(
    excel_path: str, mappings: List[SheetColumnMapping]
) -> Tuple[bool, str, List[str]]:
    """Validate an Excel file for bulletin generation.

    Args:
        excel_path: Path to the Excel file
        mappings: Column mappings for each worksheet to validate

    Returns:
        Tuple of (is_valid, error_message, valid_sheets)
    """
    try:
        xl = pd.ExcelFile(excel_path)
    except Exception as e:
        return False, f"Erreur lors de la lecture du fichier Excel: {e}", []

    if not mappings:
        return False, "Aucune feuille à valider.", []

    valid_sheets: List[str] = []
    for mapping in mappings:
        if mapping.class_name not in xl.sheet_names:
            return False, f"Onglet introuvable: {mapping.class_name}", []

        df = pd.read_excel(excel_path, sheet_name=mapping.class_name)
        is_valid, error_msg = validate_excel_structure(df, mapping)
        if not is_valid:
            return False, error_msg, []
        valid_sheets.append(mapping.class_name)

    return True, "OK", valid_sheets
