#!/usr/bin/env python3
"""
Programme pour générer des remarques de bulletins individualisées
pour les élèves de CPGE à partir d'un fichier Excel.
"""

from __future__ import annotations

import pandas as pd
import sys
import os
import logging
import argparse
from typing import Dict, List, Optional, Tuple
from openai import (
    OpenAI,
    APIError as OpenAIAPIError,
    RateLimitError,
    APIConnectionError,
)
from pydantic import BaseModel, Field

from config import APP_CONFIG
from validators import validate_excel_file


class StudentEvaluation(BaseModel):
    """Structure de sortie pour l'évaluation d'un élève."""

    remarque: str = Field(
        description="Remarque de bulletin en français, maximum 200 caractères"
    )


def setup_logging(log_level: str) -> None:
    """Configure le système de logging.

    Args:
        log_level: Niveau de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Raises:
        ValueError: Si le niveau de log est invalide
    """
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Niveau de log invalide: {log_level}")

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_openai_client() -> OpenAI:
    """Initialise le client OpenAI.

    Returns:
        OpenAI: Client OpenAI initialisé

    Raises:
        ValueError: Si la clé API n'est pas définie
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("La variable d'environnement OPENAI_API_KEY n'est pas définie")
    logging.debug("Initialisation du client OpenAI")
    return OpenAI(api_key=api_key)


def calculate_general_average(
    cb1: Optional[float], cb2: Optional[float], cb3: Optional[float]
) -> Optional[float]:
    """Calcule la moyenne générale à partir des trois concours blancs.

    Args:
        cb1: Moyenne du concours blanc 1
        cb2: Moyenne du concours blanc 2
        cb3: Moyenne du concours blanc 3

    Returns:
        La moyenne générale ou None si aucune note valide
    """
    grades = [g for g in [cb1, cb2, cb3] if g is not None and not pd.isna(g)]
    if not grades:
        return None
    return sum(grades) / len(grades)


def extract_student_data(row: pd.Series, class_type: str) -> Optional[Dict]:
    """Extrait les données d'un élève depuis une ligne du DataFrame.

    Args:
        row: Ligne du DataFrame pandas contenant les données de l'élève
        class_type: Type de classe ("ECG2" ou "KE4")

    Returns:
        Dictionnaire contenant les données de l'élève, ou None si invalide
    """
    student_num = row.iloc[0]
    last_name = row.iloc[1]
    first_name = row.iloc[2]

    # Vérifier si c'est une ligne valide (avec un nom)
    if pd.isna(last_name) or pd.isna(first_name):
        return None

    if class_type == "ECG2":
        # Première année: Compréhension, Essai, Traduction
        cb1_comp = row.get("CB1 Compréhension")
        cb1_essai = row.get("Essai")
        cb1_trad = row.get("Traduction")
        cb1_moy = row.get("Moyenne CB1")

        cb2_comp = row.get("CB2 Compréhension")
        cb2_essai = row.get("Essai.1")
        cb2_trad = row.get("Traduction.1")
        cb2_moy = row.get("Moyenne CB2")

        cb3_comp = row.get("CB3 Compréhension")
        cb3_essai = row.get("Essai.2")
        cb3_trad = row.get("Traduction.2")
        cb3_moy = row.get("Moyenne CB3")

        return {
            "num": student_num,
            "nom": last_name,
            "prenom": first_name,
            "cb1": {
                "comprehension": cb1_comp,
                "essai": cb1_essai,
                "traduction": cb1_trad,
                "moyenne": cb1_moy,
            },
            "cb2": {
                "comprehension": cb2_comp,
                "essai": cb2_essai,
                "traduction": cb2_trad,
                "moyenne": cb2_moy,
            },
            "cb3": {
                "comprehension": cb3_comp,
                "essai": cb3_essai,
                "traduction": cb3_trad,
                "moyenne": cb3_moy,
            },
            "type": "ECG2",
        }
    else:  # KE4
        # Deuxième année: Synthèse, Essai, Traduction
        cb1_synth = row.get("CB1 Synthèse")
        cb1_essai = row.get("Essai")
        cb1_trad = row.get("Traduction")
        cb1_moy = row.get("Moyenne CB1")

        cb2_synth = row.get("CB2 Synthèse")
        cb2_essai = row.get("Essai.1")
        cb2_trad = row.get("Traduction.1")
        cb2_moy = row.get("Moyenne CB2")

        cb3_synth = row.get("CB3 Synthèse")
        cb3_essai = row.get("Essai.2")
        cb3_trad = row.get("Traduction.2")
        cb3_moy = row.get("Moyenne CB3")

        return {
            "num": student_num,
            "nom": last_name,
            "prenom": first_name,
            "cb1": {
                "synthese": cb1_synth,
                "essai": cb1_essai,
                "traduction": cb1_trad,
                "moyenne": cb1_moy,
            },
            "cb2": {
                "synthese": cb2_synth,
                "essai": cb2_essai,
                "traduction": cb2_trad,
                "moyenne": cb2_moy,
            },
            "cb3": {
                "synthese": cb3_synth,
                "essai": cb3_essai,
                "traduction": cb3_trad,
                "moyenne": cb3_moy,
            },
            "type": "KE4",
        }


def format_student_data_for_prompt(student_data: Dict) -> str:
    """Formate les données de l'élève pour le prompt OpenAI.

    Args:
        student_data: Dictionnaire contenant les données de l'élève

    Returns:
        Chaîne de caractères formatée pour le prompt
    """
    logging.debug(
        f"Formatage des données pour {student_data['prenom']} {student_data['nom']}"
    )
    lines = [f"Élève: {student_data['prenom']} {student_data['nom']}"]

    if student_data["type"] == "ECG2":
        lines.append("Classe: ECG2 (Première année)")
        exercise_type = "Compréhension"
    else:
        lines.append("Classe: KE4 (Deuxième année)")
        exercise_type = "Synthèse"

    lines.append("\nRésultats des concours blancs:")

    for cb_num, cb_data in [
        ("CB1", student_data["cb1"]),
        ("CB2", student_data["cb2"]),
        ("CB3", student_data["cb3"]),
    ]:
        if student_data["type"] == "ECG2":
            comp = cb_data.get("comprehension")
            essai = cb_data.get("essai")
            trad = cb_data.get("traduction")
            moy = cb_data.get("moyenne")

            if pd.notna(moy):
                comp_str = f"{comp}" if pd.notna(comp) else "ABS"
                essai_str = f"{essai}" if pd.notna(essai) else "ABS"
                trad_str = f"{trad}" if pd.notna(trad) else "ABS"
                lines.append(
                    f"  {cb_num}: {exercise_type}={comp_str}, Essai={essai_str}, Traduction={trad_str}, Moyenne={moy}"
                )
        else:  # KE4
            synth = cb_data.get("synthese")
            essai = cb_data.get("essai")
            trad = cb_data.get("traduction")
            moy = cb_data.get("moyenne")

            if pd.notna(moy):
                synth_str = f"{synth}" if pd.notna(synth) else "ABS"
                essai_str = f"{essai}" if pd.notna(essai) else "ABS"
                trad_str = f"{trad}" if pd.notna(trad) else "ABS"
                lines.append(
                    f"  {cb_num}: {exercise_type}={synth_str}, Essai={essai_str}, Traduction={trad_str}, Moyenne={moy}"
                )

    # Calculer la moyenne générale
    moyennes = []
    for cb_data in [student_data["cb1"], student_data["cb2"], student_data["cb3"]]:
        moy = cb_data.get("moyenne")
        if pd.notna(moy):
            try:
                moyennes.append(float(moy))
            except (ValueError, TypeError):
                # Ignorer les valeurs non numériques (comme "absent", "ABS", etc.)
                pass

    if moyennes:
        moyenne_gen = sum(moyennes) / len(moyennes)
        lines.append(f"\nMoyenne générale: {moyenne_gen:.2f}/20")

    return "\n".join(lines)


def generate_evaluation(
    client: OpenAI,
    student_data: Dict,
    model: str = APP_CONFIG.DEFAULT_MODEL,
    temperature: float = APP_CONFIG.DEFAULT_TEMPERATURE,
) -> str:
    """Génère une évaluation pour un élève en utilisant l'API OpenAI.

    Args:
        client: Client OpenAI initialisé
        student_data: Dictionnaire contenant les données de l'élève
        model: Modèle OpenAI à utiliser
        temperature: Température pour la génération (0.0-1.0)

    Returns:
        Remarque de bulletin générée par l'IA
    """

    student_info = format_student_data_for_prompt(student_data)

    # Calculer la moyenne générale
    moyennes = []
    for cb_data in [student_data["cb1"], student_data["cb2"], student_data["cb3"]]:
        moy = cb_data.get("moyenne")
        if pd.notna(moy):
            try:
                moyennes.append(float(moy))
            except (ValueError, TypeError):
                # Ignorer les valeurs non numériques (comme "absent", "ABS", etc.)
                pass

    # Construire le prompt selon les guidelines
    prompt = f"""Objectif: Générer une remarque de bulletin individualisée pour cet élève, en français, à partir des résultats chiffrés.

Contraintes impératives:
* Longueur maximale : 200 caractères espaces compris
* Style : naturel, fluide et professionnel. Éviter le style télégraphique. Rédiger des phrases complètes et bien construites.
* Ne JAMAIS mentionner de notes chiffrées dans la remarque (pas de "/20", pas de moyennes, pas de chiffres)
* La remarque doit être bienveillante mais exigeante, et s'appuyer sur l'analyse des résultats sans les citer

Règles pédagogiques d'interprétation:
* Si les résultats sont faibles (moyenne < 9/20):
  - Mentionner la nécessité d'acquérir des automatismes fiables et de consolider les bases grammaticales par un travail régulier
  - Si la traduction est faible: signaler les difficultés de maîtrise grammaticale et lexicale
  - Si l'essai est faible ou moyen: souligner les faiblesses dans l'argumentation, le raisonnement ou la structuration des idées
  - Si la synthèse est faible (KE4): mentionner des difficultés méthodologiques, de hiérarchisation ou de restitution fidèle

* Si les résultats sont en progression:
  - Valoriser explicitement les progrès observés et encourager la poursuite des efforts

* Si les résultats sont solides (>= 12/20):
  - Souligner la régularité, la maîtrise des attendus et le sérieux du travail fourni

Données de l'élève:
{student_info}

Génère une remarque de bulletin individualisée en français, dans un style naturel avec des phrases complètes, sans mentionner de notes chiffrées, maximum 200 caractères."""

    try:
        # Utiliser la nouvelle API Responses avec structured outputs
        system_instruction = "Tu es un professeur d'anglais en CPGE (classe préparatoire aux grandes écoles) spécialisé dans la rédaction de remarques de bulletins claires, professionnelles et pédagogiques, 200 caractères maximum."

        full_input = f"{system_instruction}\n\n{prompt}"

        logging.info(
            f"Envoi de la requête à l'API pour {student_data['prenom']} {student_data['nom']} "
            f"(modèle: {model}, température: {temperature})"
        )
        logging.debug(f"Prompt complet:\n{full_input}")

        response = client.responses.parse(
            model=model,
            input=full_input,
            text_format=StudentEvaluation,
            temperature=temperature,
        )

        logging.debug(
            f"Réponse reçue de l'API pour {student_data['prenom']} {student_data['nom']}"
        )

        # La méthode parse retourne un ParsedResponse
        # La structure est: response.output[0].content[0].parsed
        if hasattr(response, "output") and response.output:
            if len(response.output) > 0:
                output_message = response.output[0]
                if hasattr(output_message, "content") and output_message.content:
                    if len(output_message.content) > 0:
                        output_text = output_message.content[0]
                        if hasattr(output_text, "parsed"):
                            parsed_eval = output_text.parsed
                            if isinstance(parsed_eval, StudentEvaluation):
                                logging.info(
                                    f"Évaluation générée pour {student_data['prenom']} {student_data['nom']}: "
                                    f"{parsed_eval.remarque[:50]}..."
                                )
                                return parsed_eval.remarque

        logging.error(
            f"Structure de réponse inattendue pour {student_data['prenom']} {student_data['nom']}"
        )
        logging.debug(f"Type de la réponse: {type(response)}")
        logging.debug(
            f"Attributs de la réponse: {[attr for attr in dir(response) if not attr.startswith('_')]}"
        )
        return "[Erreur: réponse invalide - structure inattendue]"

    except RateLimitError as e:
        error_msg = f"Limite de taux API atteinte pour {student_data['prenom']} {student_data['nom']}"
        logging.error(error_msg, exc_info=True)
        return "[Erreur: Limite de taux API atteinte. Veuillez réessayer plus tard.]"

    except APIConnectionError as e:
        error_msg = f"Erreur de connexion API pour {student_data['prenom']} {student_data['nom']}"
        logging.error(error_msg, exc_info=True)
        return "[Erreur: Impossible de se connecter à l'API OpenAI.]"

    except OpenAIAPIError as e:
        error_msg = f"Erreur API OpenAI pour {student_data['prenom']} {student_data['nom']}: {e}"
        logging.error(error_msg, exc_info=True)
        return f"[Erreur API: {str(e)[:100]}]"

    except Exception as e:
        logging.error(
            f"Erreur inattendue lors de la génération pour {student_data['prenom']} {student_data['nom']}: {e}",
            exc_info=True,
        )
        return "[Erreur inattendue lors de la génération de l'évaluation]"


def process_class(
    client: OpenAI,
    df: pd.DataFrame,
    class_name: str,
    class_type: str,
    model: str = APP_CONFIG.DEFAULT_MODEL,
    temperature: float = APP_CONFIG.DEFAULT_TEMPERATURE,
    max_students: Optional[int] = None,
) -> List[Tuple[str, str]]:
    """Traite tous les élèves d'une classe et retourne les évaluations avec les noms.

    Args:
        client: Client OpenAI initialisé
        df: DataFrame pandas contenant les données de la classe
        class_name: Nom de la classe (ECG2 ou KE4)
        class_type: Type de classe (ECG2 ou KE4)
        model: Modèle OpenAI à utiliser
        temperature: Température pour la génération
        max_students: Nombre maximum d'élèves à traiter (pour tests)

    Returns:
        Liste de tuples (nom_élève, évaluation)
    """
    evaluations: List[Tuple[str, str]] = []
    student_count = 0

    logging.info(f"Début du traitement de la classe {class_name}")
    logging.debug(f"Nombre total d'élèves dans le DataFrame: {len(df)}")
    if max_students:
        logging.info(f"Limite de traitement: {max_students} élèves maximum")

    for _, row in df.iterrows():
        if max_students and student_count >= max_students:
            logging.info(
                f"Limite de {max_students} élèves atteinte, arrêt du traitement"
            )
            break

        student_data = extract_student_data(row, class_type)

        if student_data is None:
            logging.debug("Ligne ignorée (données d'élève invalides)")
            continue

        student_count += 1
        student_name = f"{student_data['prenom']} {student_data['nom']}"
        logging.info(
            f"Traitement de l'élève {student_count}: {student_name} ({class_name})"
        )
        evaluation = generate_evaluation(client, student_data, model, temperature)
        evaluations.append((student_name, evaluation))

    logging.info(
        f"Traitement terminé pour {class_name}: {len(evaluations)} évaluations générées"
    )
    return evaluations


def main() -> None:
    """Fonction principale du programme CLI."""
    parser = argparse.ArgumentParser(
        description="Génère des remarques de bulletins individualisées pour les élèves de CPGE"
    )
    parser.add_argument(
        "excel_file",
        help="Fichier Excel contenant les notes des élèves (onglets ECG2 et KE4)",
    )
    parser.add_argument(
        "--log-level",
        default=APP_CONFIG.DEFAULT_LOG_LEVEL,
        choices=APP_CONFIG.VALID_LOG_LEVELS,
        help=f"Niveau de logging (défaut: {APP_CONFIG.DEFAULT_LOG_LEVEL})",
    )
    parser.add_argument(
        "--max-students",
        type=int,
        default=None,
        help="Nombre maximum d'élèves à traiter par classe (pour les tests)",
    )
    parser.add_argument(
        "--model",
        default=APP_CONFIG.DEFAULT_MODEL,
        choices=APP_CONFIG.AVAILABLE_MODELS,
        help=f"Modèle OpenAI à utiliser (défaut: {APP_CONFIG.DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=APP_CONFIG.DEFAULT_TEMPERATURE,
        help=f"Température pour la génération (défaut: {APP_CONFIG.DEFAULT_TEMPERATURE})",
    )

    args = parser.parse_args()

    # Configurer le logging
    setup_logging(args.log_level)
    logging.info("Démarrage du programme de génération d'évaluations")
    logging.info(f"Fichier Excel: {args.excel_file}")
    logging.info(f"Modèle: {args.model}, Température: {args.temperature}")
    if args.max_students:
        logging.info(f"Limite: {args.max_students} élèves par classe")

    excel_file = args.excel_file

    if not os.path.exists(excel_file):
        logging.error(f"Le fichier {excel_file} n'existe pas.")
        sys.exit(1)

    # Validate Excel file structure
    logging.info("Validation de la structure du fichier Excel...")
    is_valid, error_msg, valid_sheets = validate_excel_file(excel_file)
    if not is_valid:
        logging.error(f"Validation échouée: {error_msg}")
        sys.exit(1)

    logging.info(f"Validation réussie. Onglets valides: {', '.join(valid_sheets)}")

    # Initialiser le client OpenAI
    try:
        client = get_openai_client()
    except ValueError as e:
        logging.error(f"Erreur d'initialisation OpenAI: {e}")
        logging.info("Veuillez définir la variable d'environnement OPENAI_API_KEY")
        sys.exit(1)

    # Lire le fichier Excel
    try:
        logging.info(f"Lecture du fichier Excel: {excel_file}")
        xl = pd.ExcelFile(excel_file)
        logging.info(f"Onglets trouvés: {xl.sheet_names}")
    except Exception as e:
        logging.error(f"Erreur lors de la lecture du fichier Excel: {e}", exc_info=True)
        sys.exit(1)

    # Traiter chaque classe (use only validated sheets)
    classes = {"ECG2": "ECG2", "KE4": "KE4"}

    for class_name, class_type in classes.items():
        if class_name not in valid_sheets:
            logging.info(f"L'onglet {class_name} sera ignoré (non validé ou absent)")
            continue

        logging.info(f"Début du traitement de la classe {class_name}")
        df = pd.read_excel(excel_file, sheet_name=class_name)
        logging.debug(f"DataFrame {class_name} chargé: {len(df)} lignes")

        evaluations = process_class(
            client,
            df,
            class_name,
            class_type,
            args.model,
            args.temperature,
            args.max_students,
        )

        # Écrire le fichier de sortie
        output_file = APP_CONFIG.OUTPUT_FILE_PATTERN.format(class_name=class_name)
        logging.info(f"Écriture du fichier de sortie: {output_file}")
        with open(output_file, "w", encoding="utf-8") as f:
            for student_name, eval_text in evaluations:
                f.write(f"{student_name}: {eval_text}\n\n")

        logging.info(f"Fichier généré: {output_file} ({len(evaluations)} évaluations)")


if __name__ == "__main__":
    main()
