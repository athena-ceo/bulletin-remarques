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
    st.session_state.evaluations = {}  # {class_name: [(student_name, evaluation), ...]}
if "excel_data" not in st.session_state:
    st.session_state.excel_data = {}  # {class_name: DataFrame}
if "client" not in st.session_state:
    st.session_state.client = None
if "generating" not in st.session_state:
    st.session_state.generating = False
if "current_class" not in st.session_state:
    st.session_state.current_class = None
if "current_student_idx" not in st.session_state:
    st.session_state.current_student_idx = 0


def main() -> None:
    """Fonction principale de l'application Streamlit."""
    st.title("📝 Génération de Remarques de Bulletins")
    st.markdown("Générez des remarques individualisées pour vos élèves de CPGE.")

    # Sidebar for API configuration
    with st.sidebar:
        st.header("⚙️ Configuration")

        # API Key - get from secrets or environment
        api_key: Optional[str] = None

        # Try Streamlit secrets first
        try:
            if "OPENAI_API_KEY" in st.secrets:
                api_key = st.secrets["OPENAI_API_KEY"]
                st.success("✅ Clé API chargée depuis secrets")
        except Exception:
            pass

        # Fallback to environment variable
        if not api_key:
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                st.success("✅ Clé API chargée depuis env")
            else:
                st.error("❌ Clé API non trouvée")
                st.info(
                    "Ajoutez OPENAI_API_KEY dans .streamlit/secrets.toml ou comme variable d'environnement"
                )

        if api_key and not st.session_state.client:
            st.session_state.client = get_openai_client(api_key)

        st.divider()

        # Model selection
        model = st.selectbox(
            "Modèle OpenAI",
            APP_CONFIG.AVAILABLE_MODELS,
            index=0,
            key="model_selection",
        )

        # Temperature
        temperature = st.slider(
            "Température",
            min_value=APP_CONFIG.MIN_TEMPERATURE,
            max_value=APP_CONFIG.MAX_TEMPERATURE,
            value=APP_CONFIG.DEFAULT_TEMPERATURE,
            step=APP_CONFIG.TEMPERATURE_STEP,
            help="Contrôle la créativité (0.0 = déterministe, 1.0 = créatif)",
        )

        st.divider()

        # Help section
        with st.expander("❓ Aide", expanded=False):
            st.markdown(
                """
            ### Comment utiliser l'application
            
            **1. Configuration**
            - Assurez-vous que votre clé API OpenAI est configurée
            - Choisissez le modèle et la température selon vos besoins
            
            **2. Fichier Excel**
            - Le fichier doit contenir des onglets nommés "ECG2" et/ou "KE4"
            - ECG2 = Première année (Compréhension, Essai, Traduction)
            - KE4 = Deuxième année (Synthèse, Essai, Traduction)
            - Chaque onglet doit avoir les colonnes requises (noms, notes)
            
            **3. Génération**
            - Sélectionnez la classe (onglet) à traiter
            - (Optionnel) Limitez le nombre d'élèves pour tester
            - Cliquez sur "Générer" et attendez
            - Les évaluations apparaissent en temps réel
            
            **4. Résultats**
            - Consultez le tableau des évaluations
            - Téléchargez en TXT ou CSV
            - Changez de classe pour générer d'autres évaluations
            
            **Conseils**
            - **Température basse (0.3-0.5)**: Remarques plus cohérentes
            - **Température haute (0.7-1.0)**: Remarques plus variées
            - Les évaluations sont limitées à 200 caractères
            - Les remarques ne mentionnent jamais de notes chiffrées
            """
            )

        st.divider()
        st.caption("Bulletin Remarques Generator v2.0")

    # Main content area
    st.header("1. 📤 Télécharger le fichier Excel")

    uploaded_file = st.file_uploader(
        "Choisissez un fichier Excel avec les onglets ECG2 et/ou KE4",
        type=["xlsx", "xls"],
    )

    if uploaded_file is not None:
        try:
            # Read Excel file
            xl = pd.ExcelFile(uploaded_file)
            st.success(f"✅ Fichier chargé: {uploaded_file.name}")
            st.info(f"📋 Onglets trouvés: {', '.join(xl.sheet_names)}")

            # Store valid sheets (ECG2 and KE4 only)
            st.session_state.excel_data = {}
            for sheet_name in ["ECG2", "KE4"]:
                if sheet_name in xl.sheet_names:
                    df = pd.read_excel(uploaded_file, sheet_name=sheet_name)
                    is_valid, error_msg = validate_excel_structure(df, sheet_name)
                    if is_valid:
                        # Filter out invalid rows (Moyennes, missing names, etc.) immediately
                        valid_rows = []
                        for _, row in df.iterrows():
                            if extract_student_data(row, sheet_name) is not None:
                                valid_rows.append(row)

                        df_filtered = pd.DataFrame(valid_rows)
                        st.session_state.excel_data[sheet_name] = df_filtered

                        # Initialize evaluations for this class if not exists
                        if sheet_name not in st.session_state.evaluations:
                            st.session_state.evaluations[sheet_name] = []
                        st.success(
                            f"✅ {sheet_name}: {len(df_filtered)} élève(s) valide(s)"
                        )
                    else:
                        st.warning(f"⚠️ {sheet_name}: {error_msg}")

            if not st.session_state.excel_data:
                st.error("❌ Aucun onglet valide (ECG2 ou KE4) trouvé dans le fichier")

        except Exception as e:
            st.error(f"❌ Erreur lors de la lecture du fichier: {e}")

    # If we have data, show class selection and generation
    if st.session_state.excel_data:
        st.divider()
        st.header("2. 🎓 Sélectionner la classe")

        class_names = list(st.session_state.excel_data.keys())
        selected_class = st.selectbox(
            "Classe",
            class_names,
            key="class_selector",
        )

        if selected_class:
            df = st.session_state.excel_data[selected_class]

            st.divider()
            st.header(f"3. 📊 Données de {selected_class}")

            # Show data preview
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
                        ("✅ Complété" if existing_evals == len(df) else "⚠️ Partiel"),
                    )

            # Show Excel data
            with st.expander("Voir les données Excel", expanded=False):
                df_display = df.astype(str).replace("nan", "", regex=False)
                st.dataframe(df_display, height=300)

            st.divider()
            st.header("4. 🚀 Générer les évaluations")

            # Options for generation
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

            # Generate button
            if not st.session_state.generating:
                num_to_generate = max_students if max_students else len(df)
                if st.button(
                    f"🚀 Générer pour {num_to_generate} élève(s)",
                    type="primary",
                    disabled=not st.session_state.client,
                ):
                    # Start generation
                    st.session_state.generating = True
                    st.session_state.current_class = selected_class
                    st.session_state.current_student_idx = 0
                    st.session_state.max_students_limit = max_students
                    st.session_state.evaluations[selected_class] = []
                    st.rerun()

                if not st.session_state.client:
                    st.warning("⚠️ Configurez votre clé API dans la barre latérale")

            # Handle generation loop
            if (
                st.session_state.generating
                and st.session_state.current_class == selected_class
            ):
                df_gen = st.session_state.excel_data[st.session_state.current_class]
                class_type = st.session_state.current_class
                current_idx = st.session_state.current_student_idx
                max_limit = st.session_state.max_students_limit

                evaluations = st.session_state.evaluations[
                    st.session_state.current_class
                ]
                rows_list = list(df_gen.iterrows())

                # Check if we should continue
                should_continue = current_idx < len(rows_list) and (
                    max_limit is None or len(evaluations) < max_limit
                )

                if should_continue:
                    # Show progress
                    total_to_process = max_limit if max_limit else len(rows_list)
                    st.progress(len(evaluations) / total_to_process)
                    st.info(
                        f"⏳ Génération en cours: {len(evaluations)}/{total_to_process}"
                    )

                    # Show all evaluations generated so far
                    if evaluations:
                        st.subheader("📝 Évaluations générées:")
                        for i, (student_name, evaluation) in enumerate(evaluations, 1):
                            st.markdown(f"**{i}. {student_name}**")
                            st.info(evaluation)
                        st.divider()

                    # Process one student
                    _, row = rows_list[current_idx]
                    student_data = extract_student_data(row, class_type)

                    if student_data:
                        student_name = f"{student_data['prenom']} {student_data['nom']}"

                        with st.spinner(f"Génération pour {student_name}..."):
                            try:
                                evaluation = generate_evaluation(
                                    st.session_state.client,
                                    student_data,
                                    model,
                                    temperature,
                                )
                            except Exception as e:
                                logging.error(
                                    f"Error for {student_name}: {e}", exc_info=True
                                )
                                evaluation = f"[Erreur: {str(e)[:100]}]"

                        # Store result
                        evaluations.append((student_name, evaluation))
                        st.session_state.evaluations[st.session_state.current_class] = (
                            evaluations
                        )
                    else:
                        # Skip invalid student (missing name/prénom)
                        st.warning(
                            f"⚠️ Ligne {current_idx + 1} ignorée (nom ou prénom manquant)"
                        )

                    # Move to next student
                    st.session_state.current_student_idx += 1
                    st.rerun()
                else:
                    # Generation complete
                    st.session_state.generating = False
                    st.success(
                        f"✅ Génération terminée! {len(evaluations)} évaluation(s) créée(s)."
                    )
                    st.rerun()

            # Show results if we have any
            evaluations_for_class = st.session_state.evaluations.get(selected_class, [])
            if evaluations_for_class and not st.session_state.generating:
                st.divider()
                st.header("5. 📝 Résultats")

                st.caption(f"{len(evaluations_for_class)} évaluation(s) générée(s)")

                # Display as a list with proper text wrapping
                for i, (student_name, evaluation) in enumerate(
                    evaluations_for_class, 1
                ):
                    st.markdown(f"**{i}. {student_name}**")
                    st.info(evaluation)

                st.divider()
                st.header("6. 💾 Télécharger")

                # Create DataFrame for CSV download
                results_df = pd.DataFrame(
                    evaluations_for_class, columns=["Élève", "Remarque"]
                )

                col1, col2 = st.columns(2)

                with col1:
                    # Text file
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
                    # CSV file
                    csv_content = results_df.to_csv(index=False)
                    st.download_button(
                        label="📥 Télécharger (CSV)",
                        data=csv_content,
                        file_name=f"remarques_{selected_class}.csv",
                        mime="text/csv",
                    )


if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.WARNING)
    main()
