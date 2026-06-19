"""Column mapping models and auto-detection for Excel grade sheets."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

import pandas as pd

MainExerciseType = Literal["comprehension", "synthese"]
ColumnRole = Literal["main", "essai", "traduction", "moyenne", "simple"]

BLOCK_PREFIX_RE = re.compile(r"(?i)(CB|DST)\s*(\d+)")
COMPREHENSION_RE = re.compile(r"compr[eé]hension", re.IGNORECASE)
SYNTHESE_RE = re.compile(r"synth[eè]se|\bsyn\b", re.IGNORECASE)
ESSAI_RE = re.compile(r"^essai(?:\.(\d+))?$", re.IGNORECASE)
TRADUCTION_RE = re.compile(r"^traduction(?:\.(\d+))?$", re.IGNORECASE)
MOYENNE_RE = re.compile(r"moyenne", re.IGNORECASE)
RATTRAPAGE_RE = re.compile(r"rattrapage", re.IGNORECASE)
SIMPLE_CB_RE = re.compile(r"(?i)^CB\s*\d+\s*$")
STUDENT_INFO_RE = re.compile(r"^unnamed", re.IGNORECASE)


@dataclass
class AssessmentBlockMapping:
    """Maps one assessment block (CB/DST) to Excel columns."""

    label: str
    main_exercise_col: str
    main_exercise_type: MainExerciseType
    essai_col: str
    traduction_col: str
    moyenne_col: Optional[str] = None

    def is_simple(self) -> bool:
        """Return True when the block is a single-grade column."""
        if self.essai_col or self.traduction_col:
            return False
        if RATTRAPAGE_RE.search(self.main_exercise_col):
            return True
        return bool(SIMPLE_CB_RE.fullmatch(self.main_exercise_col.strip()))

    def required_columns(self) -> List[str]:
        """Return Excel columns required for this block."""
        cols = [self.main_exercise_col]
        if self.essai_col:
            cols.append(self.essai_col)
        if self.traduction_col:
            cols.append(self.traduction_col)
        if self.moyenne_col:
            cols.append(self.moyenne_col)
        return [col for col in cols if col]

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
            essai_col=str(data.get("essai_col", "")),
            traduction_col=str(data.get("traduction_col", "")),
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


def _infer_main_exercise_type(column_name: str) -> MainExerciseType:
    """Infer comprehension vs synthèse from a column header."""
    if COMPREHENSION_RE.search(column_name):
        return "comprehension"
    if SYNTHESE_RE.search(column_name):
        return "synthese"
    return "comprehension"


def _column_matches_exercise(column_name: str, exercise: str) -> bool:
    """Check whether a column header corresponds to an exercise type."""
    lowered = column_name.strip().lower()
    if exercise == "essai":
        return "essai" in lowered
    if exercise == "traduction":
        return "traduction" in lowered
    return False


def _block_label_from_number(prefix: str, number: str) -> str:
    """Build a normalized CB1 / DST2 label."""
    return f"{prefix.upper()}{number}"


def _classify_grade_column(column_name: str) -> Optional[Tuple[str, ColumnRole]]:
    """Classify a worksheet column into an assessment block and role."""
    col = column_name.strip()
    if not col or STUDENT_INFO_RE.match(col):
        return None

    if RATTRAPAGE_RE.search(col):
        return ("CB rattrapage", "simple")

    if MOYENNE_RE.search(col):
        numbered = BLOCK_PREFIX_RE.search(col)
        if numbered:
            label = _block_label_from_number(numbered.group(1), numbered.group(2))
            return (label, "moyenne")
        if re.search(r"\bDST\b", col, re.IGNORECASE):
            return ("DST", "moyenne")
        return None

    if re.match(r"(?i)^DST\b", col):
        if _column_matches_exercise(col, "essai"):
            return ("DST", "essai")
        if _column_matches_exercise(col, "traduction"):
            return ("DST", "traduction")
        return ("DST", "main")

    numbered = BLOCK_PREFIX_RE.search(col)
    if numbered:
        label = _block_label_from_number(numbered.group(1), numbered.group(2))
        if _column_matches_exercise(col, "essai"):
            return (label, "essai")
        if _column_matches_exercise(col, "traduction"):
            return (label, "traduction")
        if SIMPLE_CB_RE.fullmatch(col):
            return (label, "simple")
        return (label, "main")

    return None


def _ordered_duplicate_columns(
    columns: Sequence[str], pattern: re.Pattern[str]
) -> List[str]:
    """Return Essai / Traduction columns ordered by pandas duplicate suffix."""
    matched = [col for col in columns if pattern.match(col.strip())]
    return sorted(matched, key=lambda name: _suffix_order(name, pattern))


def _build_block_mapping(
    label: str, roles: Dict[str, str]
) -> Optional[AssessmentBlockMapping]:
    """Build one block mapping from grouped column roles."""
    main_col = roles.get("main") or roles.get("simple", "")
    essai_col = roles.get("essai", "")
    traduction_col = roles.get("traduction", "")
    moyenne_col = roles.get("moyenne")

    if not main_col and not essai_col and not traduction_col and not moyenne_col:
        return None

    if not main_col and moyenne_col:
        main_col = moyenne_col
        moyenne_col = None

    if not main_col:
        return None

    main_type = _infer_main_exercise_type(main_col)

    return AssessmentBlockMapping(
        label=label,
        main_exercise_col=main_col,
        main_exercise_type=main_type,
        essai_col=essai_col,
        traduction_col=traduction_col,
        moyenne_col=moyenne_col,
    )


def _legacy_fallback_blocks(columns: Sequence[str]) -> List[AssessmentBlockMapping]:
    """Detect legacy layouts with Essai / Essai.1 duplicate headers."""
    block_columns: Dict[str, List[str]] = {}
    for col in columns:
        label_match = BLOCK_PREFIX_RE.search(col)
        if not label_match:
            continue
        label = _block_label_from_number(label_match.group(1), label_match.group(2))
        block_columns.setdefault(label, []).append(col)

    if not block_columns:
        return []

    essai_cols = _ordered_duplicate_columns(columns, ESSAI_RE)
    traduction_cols = _ordered_duplicate_columns(columns, TRADUCTION_RE)
    labels = sorted(
        block_columns.keys(),
        key=lambda label: min(columns.index(col) for col in block_columns[label]),
    )

    blocks: List[AssessmentBlockMapping] = []
    for index, label in enumerate(labels):
        candidates = block_columns[label]
        main_col = next(
            (
                col
                for col in candidates
                if not _column_matches_exercise(col, "essai")
                and not _column_matches_exercise(col, "traduction")
                and not MOYENNE_RE.search(col)
            ),
            "",
        )

        essai_col = next(
            (col for col in candidates if _column_matches_exercise(col, "essai")),
            essai_cols[index] if index < len(essai_cols) else "",
        )
        traduction_col = next(
            (col for col in candidates if _column_matches_exercise(col, "traduction")),
            traduction_cols[index] if index < len(traduction_cols) else "",
        )
        moyenne_col = next((col for col in candidates if MOYENNE_RE.search(col)), None)

        block = _build_block_mapping(
            label,
            {
                "main": main_col,
                "essai": essai_col,
                "traduction": traduction_col,
                "moyenne": moyenne_col or "",
            },
        )
        if block:
            blocks.append(block)

    return blocks


def _assign_legacy_duplicate_columns(
    blocks: List[AssessmentBlockMapping], columns: Sequence[str]
) -> List[AssessmentBlockMapping]:
    """Fill missing Essai/Traduction columns from legacy duplicate headers."""
    essai_cols = _ordered_duplicate_columns(columns, ESSAI_RE)
    traduction_cols = _ordered_duplicate_columns(columns, TRADUCTION_RE)
    essai_index = 0
    traduction_index = 0
    updated_blocks: List[AssessmentBlockMapping] = []

    for block in blocks:
        essai_col = block.essai_col
        traduction_col = block.traduction_col

        if not block.is_simple():
            if not essai_col and essai_index < len(essai_cols):
                essai_col = essai_cols[essai_index]
                essai_index += 1
            if not traduction_col and traduction_index < len(traduction_cols):
                traduction_col = traduction_cols[traduction_index]
                traduction_index += 1

        updated_blocks.append(
            AssessmentBlockMapping(
                label=block.label,
                main_exercise_col=block.main_exercise_col,
                main_exercise_type=block.main_exercise_type,
                essai_col=essai_col,
                traduction_col=traduction_col,
                moyenne_col=block.moyenne_col,
            )
        )

    return updated_blocks


def auto_detect_column_mapping(
    df: pd.DataFrame, sheet_name: str
) -> SheetColumnMapping:
    """Suggest a column mapping from worksheet headers.

    Supports numbered CB/DST blocks, unnumbered DST blocks, abbreviated Syn
    headers, legacy Essai/Traduction duplicates, and single-grade columns
    such as CB5 or CB de rattrapage.
    """
    columns = _column_names(df)
    grouped_roles: Dict[str, Dict[str, str]] = defaultdict(dict)
    first_index: Dict[str, int] = {}

    for index, col in enumerate(columns):
        parsed = _classify_grade_column(col)
        if parsed is None:
            continue
        label, role = parsed
        grouped_roles[label][role] = col
        first_index.setdefault(label, index)

    blocks: List[AssessmentBlockMapping] = []
    for label in sorted(grouped_roles.keys(), key=lambda item: first_index[item]):
        block = _build_block_mapping(label, grouped_roles[label])
        if block:
            blocks.append(block)

    if not blocks:
        blocks = _legacy_fallback_blocks(columns)

    if not blocks:
        essai_cols = _ordered_duplicate_columns(columns, ESSAI_RE)
        traduction_cols = _ordered_duplicate_columns(columns, TRADUCTION_RE)
        if essai_cols or traduction_cols:
            count = max(len(essai_cols), len(traduction_cols), 2)
            for index in range(count):
                blocks.append(
                    AssessmentBlockMapping(
                        label=f"CB{index + 1}",
                        main_exercise_col="",
                        main_exercise_type="comprehension",
                        essai_col=essai_cols[index] if index < len(essai_cols) else "",
                        traduction_col=(
                            traduction_cols[index]
                            if index < len(traduction_cols)
                            else ""
                        ),
                        moyenne_col=None,
                    )
                )
    else:
        blocks = _assign_legacy_duplicate_columns(blocks, columns)

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

        if block.is_simple():
            continue

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
