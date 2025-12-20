# bulletin-remarques

Programme Python pour générer des remarques de bulletins individualisées pour les élèves de CPGE à partir d'un fichier Excel.

## ✨ Fonctionnalités

- 📊 Import de données Excel (onglets ECG2 et KE4)
- 🤖 Génération automatique d'évaluations via OpenAI
- 🎨 Interface web Streamlit intuitive
- ✅ Validation automatique des données
- 💾 Export en formats texte et CSV
- ⚡ Mise en cache pour performances optimales
- 🧪 Suite de tests unitaires

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

## 🧪 Tests

Exécutez les tests unitaires :

```bash
pytest
```

Avec couverture de code :

```bash
pytest --cov=. --cov-report=html
```

## 📁 Structure du Projet

```
bulletin-remarques/
├── config.py              # Configuration centralisée
├── exceptions.py          # Exceptions personnalisées
├── validators.py          # Validation des données Excel
├── logging_utils.py       # Logging structuré
├── generate_evaluations.py  # Script CLI principal
├── streamlit_app.py      # Interface web
├── tests/                # Tests unitaires
│   ├── __init__.py
│   └── test_bulletin.py
├── requirements.txt      # Dépendances Python
├── pyproject.toml       # Configuration des tests
└── TODO.md              # Fonctionnalités futures
```

## 🔧 Configuration Avancée

### Modèles disponibles
- `gpt-5.2` (défaut)
- `gpt-4o-mini`
- `gpt-4o`

### Paramètres de température
- `0.0` : Déterministe, reproductible
- `0.7` : Équilibré (défaut)
- `1.0` : Créatif, varié

## 🤝 Contribution

Les contributions sont les bienvenues ! Consultez `TODO.md` pour les fonctionnalités planifiées.

## 📝 Licence

Voir le fichier LICENSE pour plus de détails.
