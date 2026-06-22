#!/usr/bin/env python3
"""
Streamlit UI pour générer des remarques de bulletins individualisées
pour les élèves de CPGE à partir d'un fichier Excel.
"""

from __future__ import annotations

import hashlib
import io
import streamlit as st
import pandas as pd
import os
import logging
from typing import Dict, List, Optional, Tuple

from openai import OpenAI

from config import APP_CONFIG
from column_mapping import (
    AssessmentBlockMapping,
    SheetColumnMapping,
    auto_detect_column_mapping,
    mapping_is_complete,
)
from validators import validate_excel_structure
from generate_evaluations import (
    extract_student_data,
    format_student_data_for_prompt,
    generate_evaluation,
    get_openai_client,
)

# Configure page
st.set_page_config(
    page_title="Génération de Remarques de Bulletins",
    page_icon="📝",
    layout="wide",
)

# Initialize session state
if "evaluations" not in st.session_state:
    st.session_state.evaluations = {}
if "excel_data" not in st.session_state:
    st.session_state.excel_data = {}
if "excel_raw" not in st.session_state:
    st.session_state.excel_raw = {}
if "column_mappings" not in st.session_state:
    st.session_state.column_mappings = {}
if "client" not in st.session_state:
    st.session_state.client = None
if "uploaded_file_key" not in st.session_state:
    st.session_state.uploaded_file_key = None
if "uploaded_file_bytes" not in st.session_state:
    st.session_state.uploaded_file_bytes = None


def _column_options(df: pd.DataFrame) -> List[str]:
    """Build selectbox options from worksheet columns."""
    return [""] + [str(col) for col in df.columns]


def _ensure_block_widget_defaults(sheet_name: str, index: int) -> None:
    """Initialize widget defaults for a newly added block."""
    if f"mapping_label_{sheet_name}_{index}" not in st.session_state:
        st.session_state[f"mapping_label_{sheet_name}_{index}"] = f"CB{index + 1}"
        st.session_state[f"mapping_main_type_{sheet_name}_{index}"] = "Compréhension"
        st.session_state[f"mapping_main_col_{sheet_name}_{index}"] = ""
        st.session_state[f"mapping_essai_col_{sheet_name}_{index}"] = ""
        st.session_state[f"mapping_trad_col_{sheet_name}_{index}"] = ""
        st.session_state[f"mapping_use_moy_{sheet_name}_{index}"] = False
        st.session_state[f"mapping_moy_col_{sheet_name}_{index}"] = ""


def _build_mapping_from_ui(
    sheet_name: str, df: pd.DataFrame, num_blocks: int
) -> SheetColumnMapping:
    """Read mapping widgets and build a SheetColumnMapping."""
    column_options = _column_options(df)
    blocks: List[AssessmentBlockMapping] = []

    for index in range(num_blocks):
        _ensure_block_widget_defaults(sheet_name, index)
        label = st.text_input(
            f"Libellé bloc {index + 1}",
            key=f"mapping_label_{sheet_name}_{index}",
        )
        main_type_label = st.selectbox(
            "Exercice principal",
            ["Compréhension", "Synthèse"],
            key=f"mapping_main_type_{sheet_name}_{index}",
        )
        main_exercise_type = (
            "comprehension" if main_type_label == "Compréhension" else "synthese"
        )

        main_col = st.selectbox(
            "Colonne exercice principal",
            column_options,
            key=f"mapping_main_col_{sheet_name}_{index}",
        )
        essai_col = st.selectbox(
            "Colonne Essai",
            column_options,
            key=f"mapping_essai_col_{sheet_name}_{index}",
        )
        traduction_col = st.selectbox(
            "Colonne Traduction",
            column_options,
            key=f"mapping_trad_col_{sheet_name}_{index}",
        )
        use_moyenne_col = st.checkbox(
            "Utiliser une colonne Moyenne existante",
            key=f"mapping_use_moy_{sheet_name}_{index}",
            help="Si décoché, la moyenne sera calculée à partir des trois notes.",
        )
        moyenne_col: Optional[str] = None
        if use_moyenne_col:
            moyenne_col = st.selectbox(
                "Colonne Moyenne",
                column_options,
                key=f"mapping_moy_col_{sheet_name}_{index}",
            ) or None

        blocks.append(
            AssessmentBlockMapping(
                label=label,
                main_exercise_col=main_col,
                main_exercise_type=main_exercise_type,
                essai_col=essai_col,
                traduction_col=traduction_col,
                moyenne_col=moyenne_col,
            )
        )

    return SheetColumnMapping(class_name=sheet_name, blocks=blocks)


def _get_stored_mapping(sheet_name: str) -> SheetColumnMapping:
    """Return the auto-detected mapping stored for a worksheet."""
    return SheetColumnMapping.from_dict(
        st.session_state.column_mappings.get(
            sheet_name,
            {"class_name": sheet_name, "blocks": []},
        )
    )


def _widgets_out_of_sync(sheet_name: str, mapping: SheetColumnMapping) -> bool:
    """Return True when mapping widgets do not match the stored mapping."""
    if not mapping.blocks:
        return False
    block = mapping.blocks[0]
    expected_main = block.main_exercise_col
    actual_main = st.session_state.get(f"mapping_main_col_{sheet_name}_0", "")
    return bool(expected_main) and actual_main != expected_main


def _maybe_reseed_mapping_widgets(sheet_name: str) -> None:
    """Refresh mapping widgets when switching to a worksheet."""
    stored_mapping = _get_stored_mapping(sheet_name)
    if stored_mapping.blocks and _widgets_out_of_sync(sheet_name, stored_mapping):
        _seed_mapping_widgets(stored_mapping)


def _effective_mapping(
    sheet_name: str, ui_mapping: SheetColumnMapping
) -> SheetColumnMapping:
    """Prefer a complete UI mapping, otherwise fall back to auto-detect."""
    is_ui_complete, _ = mapping_is_complete(ui_mapping)
    if is_ui_complete:
        return ui_mapping

    stored_mapping = _get_stored_mapping(sheet_name)
    is_stored_complete, _ = mapping_is_complete(stored_mapping)
    if is_stored_complete:
        return stored_mapping

    return ui_mapping


def _register_detected_mapping(
    sheet_name: str, detected: SheetColumnMapping
) -> Optional[str]:
    """Store a detected mapping, seed widgets, and auto-apply when possible."""
    _seed_mapping_widgets(detected)
    st.session_state.column_mappings[sheet_name] = detected.to_dict()

    is_complete, message = mapping_is_complete(detected)
    if not is_complete:
        return None

    ok, apply_message = _apply_mapping(sheet_name, detected)
    if ok:
        return apply_message
    logging.warning("Auto-application échouée pour %s: %s", sheet_name, apply_message)
    return None


def _seed_mapping_widgets(mapping: SheetColumnMapping) -> None:
    """Initialize widget defaults from a detected mapping."""
    sheet_name = mapping.class_name
    st.session_state[f"num_blocks_{sheet_name}"] = max(1, len(mapping.blocks))
    for index, block in enumerate(mapping.blocks):
        st.session_state[f"mapping_label_{sheet_name}_{index}"] = block.label
        st.session_state[f"mapping_main_type_{sheet_name}_{index}"] = (
            "Compréhension"
            if block.main_exercise_type == "comprehension"
            else "Synthèse"
        )
        st.session_state[f"mapping_main_col_{sheet_name}_{index}"] = block.main_exercise_col
        st.session_state[f"mapping_essai_col_{sheet_name}_{index}"] = block.essai_col
        st.session_state[f"mapping_trad_col_{sheet_name}_{index}"] = block.traduction_col
        st.session_state[f"mapping_use_moy_{sheet_name}_{index}"] = block.moyenne_col is not None
        st.session_state[f"mapping_moy_col_{sheet_name}_{index}"] = block.moyenne_col or ""


def _apply_mapping(sheet_name: str, mapping: SheetColumnMapping) -> Tuple[bool, str]:
    """Validate mapping and store filtered student rows."""
    raw_df = st.session_state.excel_raw.get(sheet_name)
    if raw_df is None:
        return False, "Feuille introuvable."

    is_complete, message = mapping_is_complete(mapping)
    if not is_complete:
        return False, message

    is_valid, error_msg = validate_excel_structure(raw_df, mapping)
    if not is_valid:
        return False, error_msg

    valid_rows = []
    for _, row in raw_df.iterrows():
        if extract_student_data(row, mapping) is not None:
            valid_rows.append(row)

    st.session_state.column_mappings[sheet_name] = mapping.to_dict()
    st.session_state.excel_data[sheet_name] = pd.DataFrame(valid_rows)
    if sheet_name not in st.session_state.evaluations:
        st.session_state.evaluations[sheet_name] = []
    return True, f"{len(valid_rows)} élève(s) valide(s)"


def _load_excel_from_upload(uploaded_file) -> Tuple[pd.ExcelFile, str]:
    """Load workbook bytes into session state using a stable content hash."""
    file_bytes = uploaded_file.getvalue()
    file_key = hashlib.sha256(file_bytes).hexdigest()

    if st.session_state.get("uploaded_file_key") != file_key:
        st.session_state.uploaded_file_key = file_key
        st.session_state.uploaded_file_bytes = file_bytes
        st.session_state.excel_raw = {}
        st.session_state.excel_data = {}
        st.session_state.column_mappings = {}
        st.session_state.evaluations = {}

        xl = pd.ExcelFile(io.BytesIO(file_bytes))
        applied_sheets: List[str] = []
        for sheet_name in xl.sheet_names:
            df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name)
            st.session_state.excel_raw[sheet_name] = df
            detected = auto_detect_column_mapping(df, sheet_name)
            apply_message = _register_detected_mapping(sheet_name, detected)
            if apply_message:
                applied_sheets.append(f"{sheet_name} ({apply_message})")
        st.session_state.auto_applied_sheets = applied_sheets

    file_bytes = st.session_state.uploaded_file_bytes
    if file_bytes is None:
        raise ValueError("Fichier Excel non disponible en mémoire.")
    return pd.ExcelFile(io.BytesIO(file_bytes)), uploaded_file.name


def _run_generation(
    df: pd.DataFrame,
    mapping: SheetColumnMapping,
    client: OpenAI,
    model: str,
    max_students: Optional[int],
) -> List[Tuple[str, str]]:
    """Generate evaluations for all students in a single script run."""
    evaluations: List[Tuple[str, str]] = []
    rows_list = list(df.iterrows())
    total_target = max_students if max_students else len(rows_list)
    progress_bar = st.progress(0.0, text="Génération en cours...")
    status = st.empty()
    processed = 0

    for _, row in rows_list:
        if max_students is not None and processed >= max_students:
            break

        student_data = extract_student_data(row, mapping)
        if student_data is None:
            continue

        student_name = f"{student_data['prenom']} {student_data['nom']}"
        status.info(f"⏳ {processed + 1}/{total_target} — {student_name}")
        try:
            evaluation = generate_evaluation(client, student_data, model)
        except Exception as e:
            logging.error(f"Error for {student_name}: {e}", exc_info=True)
            evaluation = f"[Erreur: {str(e)[:100]}]"

        evaluations.append((student_name, evaluation))
        processed += 1
        progress_bar.progress(
            processed / total_target,
            text=f"{processed}/{total_target} élève(s)",
        )

    progress_bar.empty()
    status.empty()
    return evaluations


def main() -> None:
    """Fonction principale de l'application Streamlit."""
    st.title("📝 Génération de Remarques de Bulletins")
    st.markdown("Générez des remarques individualisées pour vos élèves de CPGE.")

    with st.sidebar:
        st.header("⚙️ Configuration")

        api_key: Optional[str] = None
        try:
            if "OPENAI_API_KEY" in st.secrets:
                api_key = st.secrets["OPENAI_API_KEY"]
                st.success("✅ Clé API chargée depuis secrets")
        except Exception:
            pass

        if not api_key:
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                st.success("✅ Clé API chargée depuis env")
            else:
                st.error("❌ Clé API non trouvée")
                st.info(
                    "Ajoutez OPENAI_API_KEY dans .streamlit/secrets.toml "
                    "ou comme variable d'environnement"
                )

        if api_key and not st.session_state.client:
            st.session_state.client = get_openai_client(api_key)

        st.divider()

        model = st.selectbox(
            "Modèle OpenAI",
            APP_CONFIG.AVAILABLE_MODELS,
            index=0,
            key="model_selection",
        )

        st.divider()

        with st.expander("❓ Aide", expanded=False):
            st.markdown(
                """
            ### Comment utiliser l'application

            **1. Configuration**
            - Assurez-vous que votre clé API OpenAI est configurée
            - Choisissez le modèle selon vos besoins

            **2. Fichier Excel**
            - Une feuille par classe (le nom de la feuille = nom de la classe)
            - Colonnes 0-2 : numéro, nom, prénom
            - Blocs CB ou DST avec Compréhension/Synthèse, Essai, Traduction
            - Moyenne optionnelle (calculée automatiquement si absente)

            **3. Correspondance des colonnes**
            - Vérifiez l'auto-détection ou mappez manuellement chaque bloc
            - Compréhension et Synthèse peuvent varier d'un bloc à l'autre
            - Cliquez sur « Appliquer le mapping » avant de générer

            **4. Génération**
            - Sélectionnez la classe à traiter
            - Cliquez sur « Générer » et attendez
            - Téléchargez les résultats en TXT ou CSV
            """
            )

        st.divider()
        st.caption("Bulletin Remarques Generator v2.1")

    st.header("1. 📤 Télécharger le fichier Excel")

    uploaded_file = st.file_uploader(
        "Choisissez un fichier Excel (une feuille par classe)",
        type=["xlsx", "xls"],
    )

    if uploaded_file is not None:
        try:
            xl, file_name = _load_excel_from_upload(uploaded_file)
            st.success(f"✅ Fichier chargé: {file_name}")
            st.info(f"📋 Onglets trouvés: {', '.join(xl.sheet_names)}")
            applied = st.session_state.get("auto_applied_sheets", [])
            if applied:
                st.success(
                    "✅ Mapping auto-détecté et appliqué pour: "
                    + ", ".join(applied)
                )
        except Exception as e:
            st.error(f"❌ Erreur lors de la lecture du fichier: {e}")

    if st.session_state.excel_raw:
        st.divider()
        st.header("2. 🎓 Sélectionner la classe")

        class_names = list(st.session_state.excel_raw.keys())
        selected_class = st.selectbox(
            "Classe",
            class_names,
            key="class_selector",
        )

        if selected_class:
            raw_df = st.session_state.excel_raw[selected_class]
            _maybe_reseed_mapping_widgets(selected_class)
            stored_mapping = _get_stored_mapping(selected_class)

            st.divider()
            st.header("3. 🧭 Correspondance des colonnes")

            if stored_mapping.blocks:
                block_summary = ", ".join(
                    f"{block.label} ({block.main_exercise_col or '?'})"
                    for block in stored_mapping.blocks
                )
                st.caption(f"Blocs détectés: {block_summary}")

            if st.button("🔍 Auto-détecter les colonnes", key=f"autodetect_{selected_class}"):
                detected = auto_detect_column_mapping(raw_df, selected_class)
                apply_message = _register_detected_mapping(selected_class, detected)
                if apply_message:
                    st.success(f"✅ Mapping appliqué: {apply_message}")
                else:
                    is_complete, message = mapping_is_complete(detected)
                    if not is_complete:
                        st.warning(message)
                st.rerun()

            default_blocks = max(1, len(stored_mapping.blocks))
            num_blocks = st.number_input(
                "Nombre de blocs (CB / DST)",
                min_value=1,
                max_value=8,
                value=max(1, default_blocks),
                key=f"num_blocks_{selected_class}",
            )

            with st.expander("Configurer les blocs", expanded=True):
                ui_mapping = _build_mapping_from_ui(selected_class, raw_df, int(num_blocks))
            mapping = _effective_mapping(selected_class, ui_mapping)

            apply_col, preview_col = st.columns([1, 2])
            with apply_col:
                if st.button("✅ Appliquer le mapping", type="primary"):
                    ok, message = _apply_mapping(selected_class, mapping)
                    if ok:
                        st.success(f"✅ Mapping appliqué: {message}")
                    else:
                        st.error(f"❌ {message}")

            with preview_col:
                is_complete, status_msg = mapping_is_complete(mapping)
                if is_complete:
                    st.info(f"Mapping prêt: {status_msg}")
                    for _, row in raw_df.iterrows():
                        preview = extract_student_data(row, mapping)
                        if preview:
                            st.caption("Aperçu du premier élève parsé:")
                            st.text(format_student_data_for_prompt(preview))
                            break
                else:
                    st.warning(status_msg)

            if selected_class in st.session_state.excel_data:
                df = st.session_state.excel_data[selected_class]

                st.divider()
                st.header(f"4. 📊 Données de {selected_class}")

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Nombre d'élèves", len(df))
                with col2:
                    existing_evals = len(
                        st.session_state.evaluations.get(selected_class, [])
                    )
                    st.metric("Évaluations existantes", existing_evals)
                with col3:
                    if existing_evals > 0:
                        st.metric(
                            "Statut",
                            (
                                "✅ Complété"
                                if existing_evals == len(df)
                                else "⚠️ Partiel"
                            ),
                        )

                with st.expander("Voir les données Excel", expanded=False):
                    df_display = df.astype(str).replace("nan", "", regex=False)
                    st.dataframe(df_display, height=300)

                st.divider()
                st.header("5. 🚀 Générer les évaluations")

                current_mapping = SheetColumnMapping.from_dict(
                    st.session_state.column_mappings[selected_class]
                )

                col1, col2 = st.columns([2, 1])
                with col1:
                    use_limit = st.checkbox(
                        "Limiter le nombre d'élèves",
                        value=False,
                        help="Générer seulement pour un nombre limité d'élèves (pour tester)",
                    )
                with col2:
                    if use_limit:
                        max_students = st.number_input(
                            "Nombre maximum",
                            min_value=1,
                            max_value=len(df),
                            value=min(5, len(df)),
                            step=1,
                        )
                    else:
                        max_students = None

                num_to_generate = max_students if max_students else len(df)
                if st.button(
                    f"🚀 Générer pour {num_to_generate} élève(s)",
                    type="primary",
                    disabled=not st.session_state.client,
                ):
                    if not st.session_state.client:
                        st.warning("⚠️ Configurez votre clé API dans la barre latérale")
                    else:
                        evaluations = _run_generation(
                            df,
                            current_mapping,
                            st.session_state.client,
                            model,
                            max_students,
                        )
                        st.session_state.evaluations[selected_class] = evaluations
                        st.success(
                            f"✅ Génération terminée! "
                            f"{len(evaluations)} évaluation(s) créée(s)."
                        )

                if not st.session_state.client:
                    st.warning("⚠️ Configurez votre clé API dans la barre latérale")

                evaluations_for_class = st.session_state.evaluations.get(
                    selected_class, []
                )
                if evaluations_for_class:
                    st.divider()
                    st.header("6. 📝 Résultats")

                    st.caption(f"{len(evaluations_for_class)} évaluation(s) générée(s)")

                    for i, (student_name, evaluation) in enumerate(
                        evaluations_for_class, 1
                    ):
                        st.markdown(f"**{i}. {student_name}**")
                        st.info(evaluation)

                    st.divider()
                    st.header("7. 💾 Télécharger")

                    results_df = pd.DataFrame(
                        evaluations_for_class, columns=["Élève", "Remarque"]
                    )

                    col1, col2 = st.columns(2)
                    with col1:
                        text_content = "\n".join(
                            [
                                f"{name}: {eval_text}\n"
                                for name, eval_text in evaluations_for_class
                            ]
                        )
                        st.download_button(
                            label="📥 Télécharger (TXT)",
                            data=text_content,
                            file_name=f"remarques_{selected_class}.txt",
                            mime="text/plain",
                        )

                    with col2:
                        csv_content = results_df.to_csv(index=False)
                        st.download_button(
                            label="📥 Télécharger (CSV)",
                            data=csv_content,
                            file_name=f"remarques_{selected_class}.csv",
                            mime="text/csv",
                        )
            else:
                st.info(
                    "Configurez et appliquez le mapping des colonnes "
                    "avant de générer les évaluations."
                )


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    main()
