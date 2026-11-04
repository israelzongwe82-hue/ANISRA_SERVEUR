# ANISRA — serveur API, première base

Fonctions préparées : inscription, connexion, profils, recherche, invitations, contacts, messages privés, groupes et dépôt de fichiers de test.

## Lancer localement
Python 3.11+ :
```bash
python -m venv .venv
pip install -r requirements.txt
uvicorn main:app --reload
```
Puis ouvrir `/docs` pour tester les routes.

## Hébergement Render
1. Mettre les fichiers de ce dossier dans un dépôt GitHub.
2. Sur Render, créer un Blueprint depuis ce dépôt et appliquer `render.yaml`.
3. Vérifier `/health` et `/docs`.
4. Garder la clé secrète dans les variables d'environnement, jamais dans le HTML ou GitHub.

## Limites à connaître avant le lancement public
- Le `index.html` actuel n'appelle pas ces nouvelles routes. Il reste intact et Israël_AI garde son intégration existante, mais l'interface n'utilisera pas encore le serveur.
- Une liaison du HTML à l'API sera indispensable pour que les utilisateurs puissent s'inscrire, se connecter et envoyer des messages. Aucune modification HTML n'a été faite.
- Les fichiers sont stockés localement dans ce prototype : prévoir un stockage cloud privé avant publication.
- Appels audio/vidéo, notifications push, chiffrement de bout en bout, récupération de compte et vérification SMS/e-mail ne sont pas encore implémentés.
- Les messages sont accessibles via API mais la diffusion instantanée WebSocket et les notifications ne sont pas encore développées.
- Avant mise en production, limiter CORS au domaine ANISRA exact, ajouter limitation de tentatives, vérification e-mail/téléphone, sauvegardes et tests de sécurité.
# ANISRA — serveur API, première base

Fonctions préparées : inscription, connexion, profils, recherche, invitations, contacts, messages privés, groupes et dépôt de fichiers de test.

## Lancer localement
Python 3.11+ :
```bash
python -m venv .venv
pip install -r requirements.txt
uvicorn main:app --reload
```
Puis ouvrir `/docs` pour tester les routes.

## Hébergement Render
1. Mettre les fichiers de ce dossier dans un dépôt GitHub.
2. Sur Render, créer un Blueprint depuis ce dépôt et appliquer `render.yaml`.
3. Vérifier `/health` et `/docs`.
4. Garder la clé secrète dans les variables d'environnement, jamais dans le HTML ou GitHub.

## Limites à connaître avant le lancement public
- Le `index.html` actuel n'appelle pas ces nouvelles routes. Il reste intact et Israël_AI garde son intégration existante, mais l'interface n'utilisera pas encore le serveur.
- Une liaison du HTML à l'API sera indispensable pour que les utilisateurs puissent s'inscrire, se connecter et envoyer des messages. Aucune modification HTML n'a été faite.
- Les fichiers sont stockés localement dans ce prototype : prévoir un stockage cloud privé avant publication.
- Appels audio/vidéo, notifications push, chiffrement de bout en bout, récupération de compte et vérification SMS/e-mail ne sont pas encore implémentés.
- Les messages sont accessibles via API mais la diffusion instantanée WebSocket et les notifications ne sont pas encore développées.
- Avant mise en production, limiter CORS au domaine ANISRA exact, ajouter limitation de tentatives, vérification e-mail/téléphone, sauvegardes et tests de sécurité.
