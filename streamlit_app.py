#!/usr/bin/env python3
"""
Streamlit UI pour générer des remarques de bulletins individualisées
pour les élèves de CPGE à partir d'un fichier Excel.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import os
import logging
from typing import Dict, List, Optional, Tuple
from openai import OpenAI

# Import functions from generate_evaluations module
import importlib.util
import sys
from pathlib import Path

from config import APP_CONFIG
from validators import validate_excel_structure

# Load generate_evaluations module
spec = importlib.util.spec_from_file_location(
    "generate_evaluations", Path(__file__).parent / "generate_evaluations.py"
)
generate_evaluations = importlib.util.module_from_spec(spec)
sys.modules["generate_evaluations"] = generate_evaluations
spec.loader.exec_module(generate_evaluations)

StudentEvaluation = generate_evaluations.StudentEvaluation
get_openai_client = generate_evaluations.get_openai_client
extract_student_data = generate_evaluations.extract_student_data
generate_evaluation = generate_evaluations.generate_evaluation

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
if "client" not in st.session_state:
    st.session_state.client = None
if "current_step" not in st.session_state:
    st.session_state.current_step = "upload"  # upload, data, results
if "generating" not in st.session_state:
    st.session_state.generating = {}  # Track which classes are being generated
if "generation_state" not in st.session_state:
    st.session_state.generation_state = {}  # Store generation progress
if "results_dataframes" not in st.session_state:
    st.session_state.results_dataframes = {}  # Store results dataframes for each class
if "show_results" not in st.session_state:
    st.session_state.show_results = False  # Flag to expand results section


def initialize_results_table(
    df: pd.DataFrame, class_name: str, class_type: str
) -> pd.DataFrame:
    """Crée un DataFrame vide avec tous les noms d'élèves pour affichage immédiat.

    Args:
        df: DataFrame source contenant les données des élèves
        class_name: Nom de la classe
        class_type: Type de classe ("ECG2" ou "KE4")

    Returns:
        DataFrame avec colonnes "Élève" et "Remarque"
    """
    student_names: List[str] = []
    rows_list = list(df.iterrows())

    for _, row in rows_list:
        student_data = extract_student_data(row, class_type)
        if student_data is not None:
            student_name = f"{student_data['prenom']} {student_data['nom']}"
            student_names.append(student_name)

    # Créer un DataFrame avec tous les noms et des remarques vides
    results_df = pd.DataFrame(
        {"Élève": student_names, "Remarque": [""] * len(student_names)}
    )
    results_df.index = range(1, len(results_df) + 1)

    return results_df


@st.cache_data(ttl=3600)
def get_student_count(df: pd.DataFrame, class_type: str) -> Dict[str, int]:
    """Cache student count calculation.

    Args:
        df: DataFrame contenant les données des élèves
        class_type: Type de classe ("ECG2" ou "KE4")

    Returns:
        Dictionnaire avec total et nombre d'élèves valides
    """
    valid_count = sum(
        1
        for _, row in df.iterrows()
        if extract_student_data(row, class_type) is not None
    )
    return {"total": len(df), "valid": valid_count}


def process_one_student(
    client: OpenAI,
    df: pd.DataFrame,
    class_name: str,
    class_type: str,
    model: str,
    temperature: float,
    current_idx: int,
    max_students: Optional[int] = None,
) -> Tuple[Optional[Tuple[str, str]], int, bool]:
    """Traite un seul élève et retourne l'évaluation, le nouvel index, et si c'est terminé."""
    rows_list = list(df.iterrows())
    total_students = len(rows_list)
    evaluations = st.session_state.evaluations.get(class_name, [])

    if max_students and len(evaluations) >= max_students:
        return None, current_idx, True

    if current_idx >= total_students:
        return None, current_idx, True

    _, row = rows_list[current_idx]
    student_data = extract_student_data(row, class_type)

    if student_data is None:
        return None, current_idx + 1, False

    student_name = f"{student_data['prenom']} {student_data['nom']}"
    evaluation = generate_evaluation(client, student_data, model, temperature)

    evaluations.append((student_name, evaluation))
    st.session_state.evaluations[class_name] = evaluations

    # Update the results dataframe immediately for each student
    if class_name in st.session_state.results_dataframes:
        # Get a copy to ensure Streamlit detects the change
        results_df = st.session_state.results_dataframes[class_name].copy()
        # Find the row for this student and update it
        mask = results_df["Élève"] == student_name
        if mask.any():
            results_df.loc[mask, "Remarque"] = evaluation
        # Reassign to trigger Streamlit state change detection
        st.session_state.results_dataframes[class_name] = results_df

    is_complete = (current_idx + 1 >= total_students) or (
        max_students and len(evaluations) >= max_students
    )

    return (student_name, evaluation), current_idx + 1, is_complete


def main() -> None:
    """Fonction principale de l'application Streamlit."""
    st.title("📝 Génération de Remarques de Bulletins")
    st.markdown(
        "Téléchargez votre fichier Excel avec les notes des élèves pour générer des remarques individualisées."
    )

    # Add custom CSS for better styling
    st.markdown(
        """
    <style>
        .stProgress > div > div > div > div {
            background-color: #00cc88;
        }
        .success-message {
            padding: 1rem;
            border-radius: 0.5rem;
            background-color: #d4edda;
            border: 1px solid #c3e6cb;
            color: #155724;
        }
        .info-box {
            padding: 1rem;
            border-radius: 0.5rem;
            background-color: #d1ecf1;
            border: 1px solid #bee5eb;
            color: #0c5460;
        }
    </style>
    """,
        unsafe_allow_html=True,
    )

    # FIRST: Display any ongoing generation progress at the top
    if any(st.session_state.generating.values()):
        for class_name in st.session_state.generating:
            if st.session_state.generating.get(class_name, False):
                current_evaluations = st.session_state.evaluations.get(class_name, [])
                gen_state = st.session_state.generation_state.get(class_name, {})
                if gen_state:
                    df = gen_state.get("df")
                    max_students = gen_state.get("max_students")
                    total = len(df) if df is not None else 0

                    # Determine what to show based on limit
                    if max_students:
                        display_total = min(max_students, total)
                        limit_text = f" (limité à {max_students})"
                    else:
                        display_total = total
                        limit_text = ""

                    st.warning(
                        f"⏳ **Génération en cours pour {class_name}**: {len(current_evaluations)}/{display_total} élèves{limit_text}"
                    )
                    if display_total > 0:
                        st.progress(len(current_evaluations) / display_total)

                    # Show ALL evaluations generated so far
                    if current_evaluations:
                        st.subheader("📝 Évaluations générées:")
                        for i, (name, eval_text) in enumerate(current_evaluations, 1):
                            st.markdown(f"**{i}. {name}**")
                            st.info(eval_text)
                        st.divider()

    # THEN: Check if we need to continue generation (process one student at a time)
    for class_name, gen_state in list(st.session_state.generation_state.items()):
        if (
            st.session_state.generating.get(class_name, False)
            and st.session_state.client
        ):
            # Process one student
            try:
                df = gen_state["df"]
                class_type = gen_state["class_type"]
                model = gen_state["model"]
                temperature = gen_state["temperature"]
                max_students = gen_state.get("max_students")
                current_idx = gen_state.get("current_idx", 0)

                result, new_idx, is_complete = process_one_student(
                    st.session_state.client,
                    df,
                    class_name,
                    class_type,
                    model,
                    temperature,
                    current_idx,
                    max_students,
                )

                if is_complete:
                    st.session_state.generating[class_name] = False
                    if class_name in st.session_state.generation_state:
                        del st.session_state.generation_state[class_name]
                    # Mark that we should expand results
                    st.session_state.show_results = True

                    # Show completion message with clear indication if limited
                    num_generated = len(
                        st.session_state.evaluations.get(class_name, [])
                    )
                    if max_students:
                        st.success(
                            f"✅ Génération terminée pour {class_name}! {num_generated} évaluation(s) créée(s) (limité à {max_students} sur {len(df)} élèves)."
                        )
                    else:
                        st.success(
                            f"✅ Génération terminée pour {class_name}! {num_generated} évaluation(s) créée(s)."
                        )

                    # Final rerun to show completion
                    st.rerun()
                else:
                    st.session_state.generation_state[class_name][
                        "current_idx"
                    ] = new_idx
                    # Rerun to process next student
                    st.rerun()

            except Exception as e:
                st.error(f"❌ Erreur lors de la génération pour {class_name}: {e}")
                st.session_state.generating[class_name] = False
                if class_name in st.session_state.generation_state:
                    del st.session_state.generation_state[class_name]
                st.exception(e)
            break

    # Sidebar for configuration
    with st.sidebar:
        st.header("⚙️ Configuration")

        # API Key - get from secrets or environment, don't display in UI
        api_key: Optional[str] = None

        # Try Streamlit secrets first
        try:
            if "OPENAI_API_KEY" in st.secrets:
                api_key = st.secrets["OPENAI_API_KEY"]
                st.success("✅ Clé API chargée depuis les secrets")
        except Exception:
            pass

        # Fall back to environment variable
        if not api_key:
            api_key = os.getenv("OPENAI_API_KEY", "")
            if api_key:
                st.success("✅ Clé API chargée depuis l'environnement")
            else:
                st.error("❌ Clé API non trouvée")
                st.info(
                    "💡 Configurez votre clé API OpenAI via:\n- Streamlit secrets (`.streamlit/secrets.toml`)\n- Variable d'environnement `OPENAI_API_KEY`"
                )

        if api_key:
            try:
                # Pass API key directly without mutating os.environ
                st.session_state.client = OpenAI(api_key=api_key)
            except Exception as e:
                st.error(f"Erreur d'initialisation du client: {e}")
                st.session_state.client = None
        else:
            st.session_state.client = None

        st.divider()

        # Model selection
        model = st.selectbox(
            "Modèle",
            APP_CONFIG.AVAILABLE_MODELS,
            index=0,
            help="Modèle OpenAI à utiliser",
        )

        # Temperature slider
        temperature = st.slider(
            "Température",
            min_value=APP_CONFIG.MIN_TEMPERATURE,
            max_value=APP_CONFIG.MAX_TEMPERATURE,
            value=APP_CONFIG.DEFAULT_TEMPERATURE,
            step=APP_CONFIG.TEMPERATURE_STEP,
            help="Contrôle la créativité des réponses (0.0 = déterministe, 1.0 = créatif)",
        )

        st.divider()

        # Max students for testing - with checkbox to enable
        enable_limit = st.checkbox(
            "Limiter le nombre d'élèves (pour tests)",
            value=False,
            help="Cochez pour traiter seulement un nombre limité d'élèves",
            key="enable_max_students",
        )

        if enable_limit:
            max_students = st.number_input(
                "Nombre d'élèves à traiter",
                min_value=1,
                value=APP_CONFIG.DEFAULT_TEST_LIMIT,
                step=1,
                help="Nombre d'élèves à traiter pour ce test",
                key="max_students_input",
            )
            st.caption(f"✓ Limite: {max_students} élève(s)")
        else:
            max_students = None
            st.caption("Tous les élèves seront traités")

        st.divider()

        # Help section
        with st.expander("ℹ️ Aide - Comment utiliser cette application"):
            st.markdown(
                """
            ### 📋 Étapes d'utilisation
            
            1. **📤 Upload** : Téléchargez votre fichier Excel contenant les notes des élèves
               - Le fichier doit contenir les onglets ECG2 (1ère année) et/ou KE4 (2ème année)
               - Format attendu : colonnes pour CB1, CB2, CB3 avec notes de compréhension/synthèse, essai, traduction
            
            2. **📊 Données** : Visualisez les données et générez les évaluations
               - Sélectionnez la classe à traiter
               - Vérifiez les données affichées
               - Cliquez sur "Générer les évaluations" pour lancer le traitement
               - Les résultats apparaîtront automatiquement dans l'onglet "Résultats"
            
            3. **📝 Résultats** : Consultez et téléchargez les évaluations
               - Les évaluations s'affichent au fur et à mesure de leur génération
               - Téléchargez les résultats en format texte (.txt) ou CSV
               - Le format texte est prêt à être copié-collé dans votre logiciel scolaire
            
            ### 💡 Conseils
            - Utilisez "Nombre max d'élèves" pour tester avec quelques élèves avant de traiter toute la classe
            - Les évaluations sont générées une par une, vous pouvez suivre la progression dans l'onglet Résultats
            - Les résultats sont sauvegardés dans la session, vous pouvez naviguer entre les onglets sans perdre les données
            """
            )

    # Main content area - Using expandable sections instead of tabs
    # Show status if generation is active
    if any(st.session_state.generating.values()):
        generating_classes = [k for k, v in st.session_state.generating.items() if v]
        for gen_class in generating_classes:
            current_eval = st.session_state.evaluations.get(gen_class, [])
            gen_state = st.session_state.generation_state.get(gen_class, {})
            df_gen = gen_state.get("df")
            max_students_limit = gen_state.get("max_students")
            total = len(df_gen) if df_gen is not None else 0

            # Determine display based on limit
            if max_students_limit:
                display_total = min(max_students_limit, total)
                limit_info = f" (limité à {max_students_limit})"
            else:
                display_total = total
                limit_info = ""

            st.info(
                f"🔄 **Génération en cours pour {gen_class}**: {len(current_eval)}/{display_total} élèves traités{limit_info} - Les résultats apparaissent dans la section '📝 Résultats' ci-dessous"
            )
            if display_total > 0:
                st.progress(len(current_eval) / display_total)

    # Section 1: Upload
    with st.expander(
        "📤 **1. Upload - Télécharger le fichier Excel**",
        expanded=not bool(st.session_state.excel_data),
    ):
        st.header("Téléchargement du fichier Excel")
        uploaded_file = st.file_uploader(
            "Choisissez un fichier Excel",
            type=["xlsx", "xls"],
            help="Le fichier doit contenir les onglets ECG2 et KE4",
        )

        if uploaded_file is not None:
            try:
                # Read Excel file
                xl = pd.ExcelFile(uploaded_file)
                st.success(f"✅ Fichier chargé: {uploaded_file.name}")
                st.info(f"Onglets trouvés: {', '.join(xl.sheet_names)}")

                # Store in session state
                st.session_state.excel_data = {}
                for sheet_name in ["ECG2", "KE4"]:
                    if sheet_name in xl.sheet_names:
                        df = pd.read_excel(uploaded_file, sheet_name=sheet_name)

                        # Validate Excel structure
                        is_valid, error_msg = validate_excel_structure(df, sheet_name)
                        if not is_valid:
                            st.error(
                                f"❌ Erreur de validation pour {sheet_name}: {error_msg}"
                            )
                            continue

                        st.session_state.excel_data[sheet_name] = df
                        st.session_state.evaluations[sheet_name] = []
                        # Initialize results table with all student names immediately
                        results_df = initialize_results_table(
                            df, sheet_name, sheet_name
                        )
                        st.session_state.results_dataframes[sheet_name] = results_df

                if "ECG2" not in xl.sheet_names and "KE4" not in xl.sheet_names:
                    st.error(
                        "⚠️ Le fichier doit contenir au moins un onglet ECG2 ou KE4"
                    )
                else:
                    st.session_state.current_step = "data"
                    st.success(
                        "✅ Fichier chargé! Ouvrez la section '📊 Données' ci-dessous pour continuer."
                    )

            except Exception as e:
                st.error(f"Erreur lors de la lecture du fichier: {e}")

    # Section 2: Data visualization and generation
    with st.expander(
        "📊 **2. Données - Visualiser et générer les évaluations**",
        expanded=bool(st.session_state.excel_data)
        and not any(st.session_state.generating.values()),
    ):
        if not st.session_state.excel_data:
            st.info(
                "📤 Veuillez d'abord télécharger un fichier Excel dans la section '📤 Upload' ci-dessus."
            )
        else:
            class_selection = st.selectbox(
                "Sélectionner la classe",
                list(st.session_state.excel_data.keys()),
                key="data_class_selection",
            )

            if class_selection:
                df = st.session_state.excel_data[class_selection]
                st.subheader(f"Données de la classe {class_selection}")

                # Show basic stats
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Nombre d'élèves", len(df))
                with col2:
                    # Use cached student count
                    stats = get_student_count(df, class_selection)
                    st.metric("Élèves valides", stats["valid"])
                with col3:
                    if st.session_state.evaluations.get(class_selection):
                        st.metric(
                            "Évaluations générées",
                            len(st.session_state.evaluations[class_selection]),
                        )

                # Display dataframe - optimize conversion to string
                df_display = df.astype(str).replace("nan", "", regex=False)
                st.dataframe(df_display, width="stretch", height=400)

                # Show existing evaluations if any
                if st.session_state.evaluations.get(class_selection):
                    st.divider()
                    st.subheader("📝 Évaluations déjà générées")
                    existing_evaluations = st.session_state.evaluations[class_selection]
                    existing_df = pd.DataFrame(
                        existing_evaluations, columns=["Élève", "Remarque"]
                    )
                    existing_df.index = range(1, len(existing_df) + 1)
                    st.dataframe(
                        existing_df,
                        width="stretch",
                        height=300,
                        column_config={
                            "Élève": st.column_config.TextColumn(
                                "Élève",
                                width="small",
                            ),
                            "Remarque": st.column_config.TextColumn(
                                "Remarque",
                                width="large",
                            ),
                        },
                    )
                    st.info(
                        f"✅ {len(existing_evaluations)} évaluations disponibles. Consultez la section '📝 Résultats' ci-dessous pour télécharger."
                    )

                # Generate evaluations button
                if st.session_state.client:
                    st.divider()

                    # Check if generation is in progress
                    is_generating = st.session_state.generating.get(
                        class_selection, False
                    )

                    if is_generating:
                        current_evaluations = st.session_state.evaluations.get(
                            class_selection, []
                        )
                        gen_state = st.session_state.generation_state.get(
                            class_selection, {}
                        )
                        current_idx = gen_state.get("current_idx", 0)
                        max_students_gen = gen_state.get("max_students")
                        total = len(df)

                        # Display based on limit
                        if max_students_gen:
                            display_total = min(max_students_gen, total)
                            st.warning(
                                f"⏳ Génération en cours... ({len(current_evaluations)}/{display_total} élèves traités - limité à {max_students_gen})"
                            )
                        else:
                            display_total = total
                            st.warning(
                                f"⏳ Génération en cours... ({len(current_evaluations)}/{display_total} élèves traités)"
                            )

                        st.progress(
                            len(current_evaluations) / display_total
                            if display_total > 0
                            else 0
                        )

                        # Show ALL evaluations generated so far in a scrollable text area
                        if current_evaluations:
                            st.subheader("📝 Évaluations générées jusqu'à présent:")
                            results_text = ""
                            for i, (name, eval_text) in enumerate(
                                current_evaluations, 1
                            ):
                                results_text += f"{i}. **{name}**\n{eval_text}\n\n"

                            st.markdown(results_text)
                            st.divider()
                    else:
                        # Show current settings before generation
                        with st.container():
                            st.caption(
                                f"Configuration: Modèle={model}, Température={temperature}, Limite élèves={max_students if max_students else 'Aucune'}"
                            )

                        if st.button(
                            f"🚀 Générer les évaluations pour {class_selection}",
                            type="primary",
                            use_container_width=True,
                        ):
                            # Initialize generation
                            st.session_state.evaluations[class_selection] = []
                            st.session_state.generating[class_selection] = True
                            st.session_state.generation_state[class_selection] = {
                                "df": df,
                                "class_type": class_selection,
                                "model": model,
                                "temperature": temperature,
                                "max_students": max_students,
                                "current_idx": 0,
                            }
                            st.session_state.current_step = "results"

                            # Show message and rerun to start generation
                            num_to_process = max_students if max_students else len(df)
                            st.success(
                                f"🚀 Génération démarrée pour {num_to_process} élève(s)! Les résultats apparaîtront en temps réel dans la section '📝 Résultats' ci-dessous."
                            )

                            # Rerun to start processing
                            st.rerun()
                else:
                    st.warning(
                        "⚠️ Veuillez configurer votre clé API dans la barre latérale"
                    )

    # Section 3: Results - Expand automatically when show_results is True
    should_expand = st.session_state.show_results or (
        bool(st.session_state.evaluations)
        and not any(st.session_state.generating.values())
    )
    with st.expander(
        "📝 **3. Résultats - Voir et télécharger les évaluations**",
        expanded=should_expand,
    ):
        # Check if generation is in progress
        generating_classes = [k for k, v in st.session_state.generating.items() if v]

        # Check if there are any evaluations
        has_evaluations = bool(st.session_state.evaluations) and any(
            st.session_state.evaluations.values()
        )

        # Check if there are classes with data
        has_data = bool(st.session_state.excel_data)

        if not has_data:
            st.info(
                "📝 Aucune évaluation générée. Commencez par télécharger un fichier dans la section '📤 Upload'."
            )
        else:
            # Select class to display
            all_classes = list(st.session_state.excel_data.keys())

            if all_classes:
                selected_class = st.selectbox(
                    "Sélectionner la classe",
                    all_classes,
                    key="results_class_selection",
                )

                # Get or create results dataframe for this class
                # Always read fresh from session state
                if selected_class in st.session_state.results_dataframes:
                    results_df = st.session_state.results_dataframes[selected_class]
                else:
                    # Create empty results table if it doesn't exist
                    df = st.session_state.excel_data[selected_class]
                    results_df = initialize_results_table(
                        df, selected_class, selected_class
                    )
                    st.session_state.results_dataframes[selected_class] = results_df

                # Show progress if generating
                if selected_class in generating_classes:
                    current_eval = st.session_state.evaluations.get(selected_class, [])
                    gen_state = st.session_state.generation_state.get(
                        selected_class, {}
                    )
                    df_gen = gen_state.get("df")
                    total = len(df_gen) if df_gen is not None else 0

                    st.info(
                        f"⏳ Génération en cours pour {selected_class}: {len(current_eval)}/{total} élèves traités"
                    )
                    if total > 0:
                        st.progress(len(current_eval) / total)

                # Display results table - re-read from session state on every render
                st.subheader(f"Évaluations pour {selected_class}")

                # Count completed evaluations and show info about subset if applicable
                completed = len([r for r in results_df["Remarque"] if r != ""])
                total_students = len(results_df)
                evaluations = st.session_state.evaluations.get(selected_class, [])

                # Check if this was a limited generation
                if evaluations and len(evaluations) < total_students:
                    st.info(
                        f"ℹ️ **Génération partielle**: {completed} évaluation(s) générée(s) sur {total_students} élèves au total"
                    )
                    st.caption(f"✅ {completed} évaluations complétées (sous-ensemble)")
                else:
                    st.caption(
                        f"✅ {completed}/{total_students} évaluations complétées"
                    )

                # Display the table - no real-time updates, just show final state
                st.dataframe(
                    results_df,
                    width="stretch",
                    height=600,
                    column_config={
                        "Élève": st.column_config.TextColumn(
                            "Élève",
                            width="small",
                        ),
                        "Remarque": st.column_config.TextColumn(
                            "Remarque",
                            width="large",
                        ),
                    },
                )

                # No auto-refresh - wait for completion

                # Download buttons (only show if there are completed evaluations)
                evaluations = st.session_state.evaluations.get(selected_class, [])
                # Use display_df for CSV download
                if evaluations:
                    st.divider()
                    col1, col2 = st.columns(2)

                    with col1:
                        # Create text file content
                        text_content = "\n".join(
                            [
                                f"{name}: {eval_text}\n"
                                for name, eval_text in evaluations
                            ]
                        )

                        st.download_button(
                            label="📥 Télécharger le fichier texte",
                            data=text_content,
                            file_name=f"remarques_{selected_class}.txt",
                            mime="text/plain",
                            width="stretch",
                        )

                    with col2:
                        # Download as CSV - only completed rows
                        csv_df_completed = results_df[results_df["Remarque"] != ""]
                        csv_content = csv_df_completed.to_csv(index=False)
                        st.download_button(
                            label="📥 Télécharger en CSV",
                            data=csv_content,
                            file_name=f"remarques_{selected_class}.csv",
                            mime="text/csv",
                            width="stretch",
                        )

                    # Show preview of text file
                    st.subheader("Aperçu du fichier texte")
                    st.text_area(
                        "Contenu du fichier",
                        text_content,
                        height=300,
                        label_visibility="collapsed",
                    )


if __name__ == "__main__":
    # Setup logging (suppress verbose logs in Streamlit)
    logging.basicConfig(level=logging.WARNING)
    main()
