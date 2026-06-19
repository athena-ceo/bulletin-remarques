"""Column mapping models and auto-detection for Excel grade sheets."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

import pandas as pd

MainExerciseType = Literal["comprehension", "synthese"]

BLOCK_PREFIX_RE = re.compile(r"(?i)(CB|DST)\s*(\d+)")
COMPREHENSION_RE = re.compile(r"compr[eé]hension", re.IGNORECASE)
SYNTHESE_RE = re.compile(r"synth[eè]se", re.IGNORECASE)
ESSAI_RE = re.compile(r"^essai(?:\.(\d+))?$", re.IGNORECASE)
TRADUCTION_RE = re.compile(r"^traduction(?:\.(\d+))?$", re.IGNORECASE)
MOYENNE_RE = re.compile(r"moyenne", re.IGNORECASE)


@dataclass
class AssessmentBlockMapping:
    """Maps one assessment block (CB/DST) to Excel columns."""

    label: str
    main_exercise_col: str
    main_exercise_type: MainExerciseType
    essai_col: str
    traduction_col: str
    moyenne_col: Optional[str] = None

    def required_columns(self) -> List[str]:
        """Return Excel columns required for this block."""
        cols = [self.main_exercise_col, self.essai_col, self.traduction_col]
        if self.moyenne_col:
            cols.append(self.moyenne_col)
        return cols

    def to_dict(self) -> Dict[str, Any]:
        """Serialize block mapping for session state."""
        return {
            "label": self.label,
            "main_exercise_col": self.main_exercise_col,
            "main_exercise_type": self.main_exercise_type,
            "essai_col": self.essai_col,
            "traduction_col": self.traduction_col,
            "moyenne_col": self.moyenne_col,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AssessmentBlockMapping:
        """Deserialize block mapping from session state."""
        return cls(
            label=str(data["label"]),
            main_exercise_col=str(data["main_exercise_col"]),
            main_exercise_type=data["main_exercise_type"],
            essai_col=str(data["essai_col"]),
            traduction_col=str(data["traduction_col"]),
            moyenne_col=data.get("moyenne_col"),
        )


@dataclass
class SheetColumnMapping:
    """Complete column mapping for one class worksheet."""

    class_name: str
    blocks: List[AssessmentBlockMapping] = field(default_factory=list)
    student_num_col: int = 0
    last_name_col: int = 1
    first_name_col: int = 2

    def required_columns(self) -> List[str]:
        """Return all grade columns required by this mapping."""
        cols: List[str] = []
        for block in self.blocks:
            cols.extend(block.required_columns())
        return list(dict.fromkeys(cols))

    def to_dict(self) -> Dict[str, Any]:
        """Serialize sheet mapping for session state."""
        return {
            "class_name": self.class_name,
            "blocks": [block.to_dict() for block in self.blocks],
            "student_num_col": self.student_num_col,
            "last_name_col": self.last_name_col,
            "first_name_col": self.first_name_col,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SheetColumnMapping:
        """Deserialize sheet mapping from session state."""
        return cls(
            class_name=str(data["class_name"]),
            blocks=[AssessmentBlockMapping.from_dict(b) for b in data.get("blocks", [])],
            student_num_col=int(data.get("student_num_col", 0)),
            last_name_col=int(data.get("last_name_col", 1)),
            first_name_col=int(data.get("first_name_col", 2)),
        )


def _column_names(df: pd.DataFrame) -> List[str]:
    """Return DataFrame column names as strings."""
    return [str(col) for col in df.columns]


def _suffix_order(name: str, pattern: re.Pattern[str]) -> int:
    """Order Essai / Essai.1 / Essai.2 columns for block assignment."""
    match = pattern.match(name.strip())
    if not match:
        return 999
    suffix = match.group(1)
    return 0 if suffix is None else int(suffix)


def _block_sort_key(label: str) -> Tuple[str, int]:
    """Sort CB1, CB2, DST1, DST2 in a stable order."""
    match = BLOCK_PREFIX_RE.search(label)
    if not match:
        return ("ZZ", 999)
    return (match.group(1).upper(), int(match.group(2)))


def _infer_main_exercise_type(column_name: str) -> Optional[MainExerciseType]:
    """Infer comprehension vs synthèse from a column header."""
    if COMPREHENSION_RE.search(column_name):
        return "comprehension"
    if SYNTHESE_RE.search(column_name):
        return "synthese"
    return None


def _block_label_from_column(column_name: str) -> Optional[str]:
    """Extract CB1 / DST2 label from a column header."""
    match = BLOCK_PREFIX_RE.search(column_name)
    if not match:
        return None
    return f"{match.group(1).upper()}{match.group(2)}"


def _column_matches_exercise(column_name: str, exercise: str) -> bool:
    """Check whether a column header corresponds to an exercise type."""
    lowered = column_name.strip().lower()
    if exercise == "essai":
        return "essai" in lowered
    if exercise == "traduction":
        return "traduction" in lowered
    return False


def _find_exercise_column(columns: Sequence[str], exercise: str) -> Optional[str]:
    """Pick Essai or Traduction column from block candidates."""
    for col in columns:
        if _column_matches_exercise(col, exercise):
            return col
    return None


def _find_main_column(columns: Sequence[str]) -> Optional[str]:
    """Pick the main exercise column from a list of candidate headers."""
    for col in columns:
        if _infer_main_exercise_type(col) is not None:
            return col
    return None


def _find_moyenne_column(columns: Sequence[str], label: str) -> Optional[str]:
    """Pick the moyenne column for a block."""
    label_match = BLOCK_PREFIX_RE.search(label)
    for col in columns:
        if not MOYENNE_RE.search(col):
            continue
        col_label = _block_label_from_column(col)
        if col_label == label:
            return col
    for col in columns:
        if MOYENNE_RE.search(col) and label.lower() in col.lower():
            return col
    return None


def _ordered_duplicate_columns(
    columns: Sequence[str], pattern: re.Pattern[str]
) -> List[str]:
    """Return Essai / Traduction columns ordered by pandas duplicate suffix."""
    matched = [col for col in columns if pattern.match(col.strip())]
    return sorted(matched, key=lambda name: _suffix_order(name, pattern))


def auto_detect_column_mapping(
    df: pd.DataFrame, sheet_name: str
) -> SheetColumnMapping:
    """Suggest a column mapping from worksheet headers.

    Uses CB/DST prefixes when present and falls back to ordered Essai/Traduction
    columns for blocks that share unprefixed duplicate headers.
    """
    columns = _column_names(df)
    block_columns: Dict[str, List[str]] = {}

    for col in columns:
        label = _block_label_from_column(col)
        if label:
            block_columns.setdefault(label, []).append(col)

    for col in columns:
        if not MOYENNE_RE.search(col):
            continue
        label = _block_label_from_column(col)
        if label:
            block_columns.setdefault(label, []).append(col)

    labels = sorted(block_columns.keys(), key=_block_sort_key)
    essai_cols = _ordered_duplicate_columns(columns, ESSAI_RE)
    traduction_cols = _ordered_duplicate_columns(columns, TRADUCTION_RE)

    blocks: List[AssessmentBlockMapping] = []
    for index, label in enumerate(labels):
        candidates = block_columns.get(label, [])
        main_col = _find_main_column(candidates)
        moyenne_col = _find_moyenne_column(candidates, label)

        essai_col = _find_exercise_column(candidates, "essai") or (
            essai_cols[index] if index < len(essai_cols) else ""
        )
        traduction_col = _find_exercise_column(candidates, "traduction") or (
            traduction_cols[index] if index < len(traduction_cols) else ""
        )

        main_type: MainExerciseType = "comprehension"
        if main_col:
            inferred = _infer_main_exercise_type(main_col)
            if inferred:
                main_type = inferred

        if not main_col and not essai_col and not traduction_col and not moyenne_col:
            continue

        blocks.append(
            AssessmentBlockMapping(
                label=label,
                main_exercise_col=main_col or "",
                main_exercise_type=main_type,
                essai_col=essai_col or "",
                traduction_col=traduction_col or "",
                moyenne_col=moyenne_col,
            )
        )

    if not blocks and (essai_cols or traduction_cols):
        count = max(len(essai_cols), len(traduction_cols), 2)
        for index in range(count):
            blocks.append(
                AssessmentBlockMapping(
                    label=f"CB{index + 1}",
                    main_exercise_col="",
                    main_exercise_type="comprehension",
                    essai_col=essai_cols[index] if index < len(essai_cols) else "",
                    traduction_col=(
                        traduction_cols[index] if index < len(traduction_cols) else ""
                    ),
                    moyenne_col=None,
                )
            )

    return SheetColumnMapping(class_name=sheet_name, blocks=blocks)


def compute_block_moyenne(
    main: Any, essai: Any, traduction: Any
) -> Optional[float]:
    """Compute block average from exercise grades when moyenne is absent."""
    grades: List[float] = []
    for value in (main, essai, traduction):
        if value is None or pd.isna(value):
            continue
        try:
            grades.append(float(value))
        except (TypeError, ValueError):
            continue
    if not grades:
        return None
    return sum(grades) / len(grades)


def mapping_is_complete(mapping: SheetColumnMapping) -> Tuple[bool, str]:
    """Check whether a mapping is ready for extraction."""
    if not mapping.blocks:
        return False, "Ajoutez au moins un bloc d'évaluation (CB ou DST)."

    for block in mapping.blocks:
        if not block.label.strip():
            return False, "Chaque bloc doit avoir un libellé (ex. CB1, DST2)."
        if not block.main_exercise_col:
            return False, f"{block.label}: colonne d'exercice principal manquante."
        if not block.essai_col:
            return False, f"{block.label}: colonne Essai manquante."
        if not block.traduction_col:
            return False, f"{block.label}: colonne Traduction manquante."

        for required_col in block.required_columns():
            if not required_col:
                return False, f"{block.label}: colonne requise non sélectionnée."

    assigned = mapping.required_columns()
    if len(assigned) != len(set(assigned)):
        return False, "Une même colonne est utilisée pour plusieurs champs."

    return True, "OK"
