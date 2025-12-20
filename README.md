# bulletin-remarques

Programme Python pour générer des remarques de bulletins individualisées pour les élèves de CPGE à partir d'un fichier Excel.

## Installation

1. Activer l'environnement virtuel :
```bash
source brvenv/bin/activate
```

2. Installer les dépendances :
```bash
pip install -r requirements.txt
```

3. Configurer la clé API OpenAI :

**Option 1 : Variable d'environnement (recommandé pour développement local)**
```bash
export OPENAI_API_KEY="votre-clé-api"
```

**Option 2 : Secrets Streamlit (recommandé pour production)**

Créez un fichier `.streamlit/secrets.toml` :
```toml
OPENAI_API_KEY = "votre-clé-api"
```

Note: Le fichier `secrets.toml` ne doit jamais être commis dans git. Ajoutez `.streamlit/` à votre `.gitignore`.

## Utilisation

### Interface Web (Streamlit) - Recommandé

Lancez l'interface web Streamlit :

```bash
streamlit run streamlit_app.py
```

L'interface s'ouvrira dans votre navigateur. Vous pourrez :
- Télécharger votre fichier Excel
- Visualiser les données
- Configurer les paramètres (modèle, température)
- Générer les évaluations avec une barre de progression
- Visualiser les résultats dans un tableau
- Télécharger les fichiers de résultats (texte ou CSV)

### Ligne de commande

```bash
python generate_evaluations.py <fichier_excel>
```

Exemple :
```bash
python generate_evaluations.py "Notes 2025-26.xlsx"
```

## Format du fichier Excel

Le fichier Excel doit contenir deux onglets :
- **ECG2** : Élèves de première année (Compréhension, Essai, Traduction)
- **KE4** : Élèves de deuxième année (Synthèse, Essai, Traduction)

Chaque onglet doit contenir les colonnes suivantes :
- Colonnes 0-2 : Numéro, Nom, Prénom
- Pour chaque concours blanc (CB1, CB2, CB3) :
  - Notes des exercices (Compréhension/Synthèse, Essai, Traduction)
  - Moyenne du concours blanc

## Sortie

Le programme génère deux fichiers texte :
- `remarques_ECG2.txt` : Remarques pour les élèves de première année
- `remarques_KE4.txt` : Remarques pour les élèves de deuxième année

Chaque fichier contient une remarque par ligne, prête à être copiée-collée dans le logiciel scolaire.
