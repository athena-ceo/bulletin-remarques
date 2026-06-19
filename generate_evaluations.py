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
import httpx
from typing import Any, Dict, List, Optional, Tuple
from openai import (
    OpenAI,
    APIError as OpenAIAPIError,
    RateLimitError,
    APIConnectionError,
)
from pydantic import BaseModel, Field

from config import APP_CONFIG
from column_mapping import SheetColumnMapping, auto_detect_column_mapping, compute_block_moyenne
from validators import validate_excel_file, validate_excel_structure


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


def get_openai_client(api_key: Optional[str] = None) -> OpenAI:
    """Initialise le client OpenAI.

    Args:
        api_key: Clé API OpenAI (optionnel, utilise OPENAI_API_KEY si non fourni)

    Returns:
        OpenAI: Client OpenAI initialisé

    Raises:
        ValueError: Si la clé API n'est pas définie
    """
    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("La clé API OpenAI n'est pas définie")
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


def extract_student_data(
    row: pd.Series, mapping: SheetColumnMapping
) -> Optional[Dict]:
    """Extrait les données d'un élève depuis une ligne du DataFrame.

    Args:
        row: Ligne du DataFrame pandas contenant les données de l'élève
        mapping: Correspondance des colonnes pour la feuille

    Returns:
        Dictionnaire contenant les données de l'élève, ou None si invalide
    """
    student_num = row.iloc[mapping.student_num_col]
    last_name = row.iloc[mapping.last_name_col]
    first_name = row.iloc[mapping.first_name_col]

    # Skip rows that are summary rows (averages, etc.) - check this FIRST
    # before checking for missing names
    if not pd.isna(last_name):
        last_name_str = str(last_name).strip().lower()
        if any(
            keyword in last_name_str
            for keyword in ["moyenne", "moyennes", "total", "somme"]
        ):
            return None

    # Vérifier si c'est une ligne valide (avec un nom et prénom)
    if pd.isna(last_name) or pd.isna(first_name):
        return None

    assessments: List[Dict] = []
    for block in mapping.blocks:
        main = row.get(block.main_exercise_col)
        essai = row.get(block.essai_col) if block.essai_col else pd.NA
        traduction = row.get(block.traduction_col) if block.traduction_col else pd.NA

        if block.moyenne_col:
            moyenne = row.get(block.moyenne_col)
        else:
            moyenne = compute_block_moyenne(main, essai, traduction)

        assessments.append(
            {
                "label": block.label,
                "main_type": block.main_exercise_type,
                "main": main,
                "essai": essai,
                "traduction": traduction,
                "moyenne": moyenne,
            }
        )

    return {
        "num": student_num,
        "nom": last_name,
        "prenom": first_name,
        "class_name": mapping.class_name,
        "assessments": assessments,
    }


def _main_exercise_label(main_type: str) -> str:
    """Return the French label for a main exercise type."""
    return "Compréhension" if main_type == "comprehension" else "Synthèse"


def _format_grade(value: Any) -> str:
    """Format a grade value for the prompt."""
    return f"{value}" if pd.notna(value) else "ABS"


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
    lines.append(f"Classe: {student_data['class_name']}")
    lines.append("\nRésultats des évaluations:")

    for assessment in student_data["assessments"]:
        moy = assessment.get("moyenne")
        if pd.isna(moy):
            continue

        label = assessment["label"]
        if pd.isna(assessment.get("essai")) and pd.isna(assessment.get("traduction")):
            lines.append(f"  {label}: Moyenne={moy}")
            continue

        exercise_label = _main_exercise_label(assessment["main_type"])
        main_str = _format_grade(assessment.get("main"))
        essai_str = _format_grade(assessment.get("essai"))
        trad_str = _format_grade(assessment.get("traduction"))
        lines.append(
            f"  {label}: {exercise_label}={main_str}, "
            f"Essai={essai_str}, Traduction={trad_str}, Moyenne={moy}"
        )

    moyennes: List[float] = []
    for assessment in student_data["assessments"]:
        moy = assessment.get("moyenne")
        if pd.notna(moy):
            try:
                moyennes.append(float(moy))
            except (ValueError, TypeError):
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
    max_retries: int = 3,
) -> str:
    """Génère une évaluation pour un élève en utilisant l'API OpenAI.

    Args:
        client: Client OpenAI initialisé
        student_data: Dictionnaire contenant les données de l'élève
        model: Modèle OpenAI à utiliser
        temperature: Température pour la génération (0.0-1.0)
        max_retries: Nombre maximum de tentatives si la longueur dépasse 200 caractères

    Returns:
        Remarque de bulletin générée par l'IA
    """

    student_info = format_student_data_for_prompt(student_data)

    moyennes: List[float] = []
    for assessment in student_data["assessments"]:
        moy = assessment.get("moyenne")
        if pd.notna(moy):
            try:
                moyennes.append(float(moy))
            except (ValueError, TypeError):
                pass

    for attempt in range(max_retries):
        # Construire le prompt selon les guidelines, plus strict à chaque tentative
        strictness_note = ""
        if attempt > 0:
            strictness_note = f"\n\n⚠️ ATTENTION: Tentative {attempt + 1}/{max_retries}. La remarque précédente était trop longue. Vous DEVEZ respecter la limite de 200 caractères. Soyez plus concis et direct."

        prompt = f"""Objectif: Générer une remarque de bulletin individualisée pour cet élève, en français, à partir des résultats chiffrés.

Contraintes impératives:
* Longueur maximale STRICTE : 200 caractères espaces compris (IMPÉRATIF - comptez les caractères!)
* Utiliser "CB" au lieu de "Concours Blanc" pour économiser des caractères
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
{strictness_note}

Génère une remarque de bulletin individualisée en français, dans un style naturel avec des phrases complètes, sans mentionner de notes chiffrées, MAXIMUM 200 CARACTÈRES (incluant espaces et ponctuation)."""

        try:
            # Utiliser la nouvelle API Responses avec structured outputs
            system_instruction = "Tu es un professeur d'anglais en CPGE spécialisé dans la rédaction de remarques de bulletins claires, professionnelles et pédagogiques. Tu dois IMPÉRATIVEMENT respecter la limite de 200 caractères. Utilise 'CB' au lieu de 'Concours Blanc'."

            full_input = f"{system_instruction}\n\n{prompt}"

            logging.info(
                f"Envoi de la requête à l'API pour {student_data['prenom']} {student_data['nom']} "
                f"(modèle: {model}, température: {temperature}, tentative: {attempt + 1}/{max_retries})"
            )
            logging.debug(f"Prompt complet:\n{full_input}")

            # Add timeout to the API call (60 seconds total, 10 seconds to connect)
            timeout = httpx.Timeout(60.0, connect=10.0)

            response = client.responses.parse(
                model=model,
                input=full_input,
                text_format=StudentEvaluation,
                temperature=temperature,
                timeout=timeout,
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
                                    remarque = parsed_eval.remarque
                                    remarque_length = len(remarque)

                                    # Vérifier la longueur
                                    if remarque_length <= APP_CONFIG.MAX_REMARK_LENGTH:
                                        logging.info(
                                            f"Évaluation générée pour {student_data['prenom']} {student_data['nom']}: "
                                            f"{remarque[:50]}... ({remarque_length} caractères)"
                                        )
                                        return remarque
                                    else:
                                        logging.warning(
                                            f"Remarque trop longue pour {student_data['prenom']} {student_data['nom']}: "
                                            f"{remarque_length} caractères (max: {APP_CONFIG.MAX_REMARK_LENGTH}). "
                                            f"Tentative {attempt + 1}/{max_retries}"
                                        )
                                        if attempt < max_retries - 1:
                                            continue  # Retry
                                        else:
                                            # Dernière tentative échouée, tronquer la remarque
                                            logging.error(
                                                f"Impossible de générer une remarque ≤ 200 caractères après {max_retries} tentatives. "
                                                f"Troncature de la remarque."
                                            )
                                            return remarque[
                                                : APP_CONFIG.MAX_REMARK_LENGTH
                                            ]

            logging.error(
                f"Structure de réponse inattendue pour {student_data['prenom']} {student_data['nom']}"
            )
            logging.debug(f"Type de la réponse: {type(response)}")
            logging.debug(
                f"Attributs de la réponse: {[attr for attr in dir(response) if not attr.startswith('_')]}"
            )
            return "[Erreur: réponse invalide - structure inattendue]"

        except httpx.TimeoutException as e:
            error_msg = f"Timeout lors de la génération pour {student_data['prenom']} {student_data['nom']} (tentative {attempt + 1}/{max_retries})"
            logging.error(error_msg, exc_info=True)
            if attempt < max_retries - 1:
                logging.info(f"Nouvelle tentative après timeout...")
                continue  # Retry
            else:
                return "[Erreur: Timeout - L'API a mis trop de temps à répondre après plusieurs tentatives.]"

        except RateLimitError as e:
            error_msg = f"Limite de taux API atteinte pour {student_data['prenom']} {student_data['nom']}"
            logging.error(error_msg, exc_info=True)
            return (
                "[Erreur: Limite de taux API atteinte. Veuillez réessayer plus tard.]"
            )

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

    # Si on arrive ici, toutes les tentatives ont échoué
    return "[Erreur: impossible de générer une évaluation valide]"


def process_class(
    client: OpenAI,
    df: pd.DataFrame,
    mapping: SheetColumnMapping,
    model: str = APP_CONFIG.DEFAULT_MODEL,
    temperature: float = APP_CONFIG.DEFAULT_TEMPERATURE,
    max_students: Optional[int] = None,
) -> List[Tuple[str, str]]:
    """Traite tous les élèves d'une classe et retourne les évaluations avec les noms.

    Args:
        client: Client OpenAI initialisé
        df: DataFrame pandas contenant les données de la classe
        mapping: Correspondance des colonnes pour la feuille
        model: Modèle OpenAI à utiliser
        temperature: Température pour la génération
        max_students: Nombre maximum d'élèves à traiter (pour tests)

    Returns:
        Liste de tuples (nom_élève, évaluation)
    """
    evaluations: List[Tuple[str, str]] = []
    student_count = 0
    class_name = mapping.class_name

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

        student_data = extract_student_data(row, mapping)

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
        help="Fichier Excel contenant une feuille par classe",
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

    # Lire le fichier Excel et détecter automatiquement les correspondances
    try:
        logging.info(f"Lecture du fichier Excel: {excel_file}")
        xl = pd.ExcelFile(excel_file)
        logging.info(f"Onglets trouvés: {xl.sheet_names}")
    except Exception as e:
        logging.error(f"Erreur lors de la lecture du fichier Excel: {e}", exc_info=True)
        sys.exit(1)

    mappings: List[SheetColumnMapping] = []
    for sheet_name in xl.sheet_names:
        df_preview = pd.read_excel(excel_file, sheet_name=sheet_name)
        mapping = auto_detect_column_mapping(df_preview, sheet_name)
        mappings.append(mapping)

    logging.info("Validation de la structure du fichier Excel...")
    is_valid, error_msg, valid_sheets = validate_excel_file(excel_file, mappings)
    if not is_valid:
        logging.error(f"Validation échouée: {error_msg}")
        logging.info(
            "Utilisez l'interface Streamlit pour ajuster manuellement les colonnes."
        )
        sys.exit(1)

    logging.info(f"Validation réussie. Onglets valides: {', '.join(valid_sheets)}")

    try:
        client = get_openai_client()
    except ValueError as e:
        logging.error(f"Erreur d'initialisation OpenAI: {e}")
        logging.info("Veuillez définir la variable d'environnement OPENAI_API_KEY")
        sys.exit(1)

    for mapping in mappings:
        if mapping.class_name not in valid_sheets:
            continue

        logging.info(f"Début du traitement de la classe {mapping.class_name}")
        df = pd.read_excel(excel_file, sheet_name=mapping.class_name)
        logging.debug(f"DataFrame {mapping.class_name} chargé: {len(df)} lignes")

        evaluations = process_class(
            client,
            df,
            mapping,
            args.model,
            args.temperature,
            args.max_students,
        )

        output_file = APP_CONFIG.OUTPUT_FILE_PATTERN.format(
            class_name=mapping.class_name
        )
        logging.info(f"Écriture du fichier de sortie: {output_file}")
        with open(output_file, "w", encoding="utf-8") as f:
            for student_name, eval_text in evaluations:
                f.write(f"{student_name}: {eval_text}\n\n")

        logging.info(
            f"Fichier généré: {output_file} ({len(evaluations)} évaluations)"
        )


if __name__ == "__main__":
    main()
