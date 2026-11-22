# Smartwatch santé — pipeline ML + API (mock data)

## Lancer
```bash
pip install numpy pandas scikit-learn scipy joblib matplotlib flask
python generate_data.py     # données mock (40 patients x 2 jours, 1 mesure/min)
python train.py             # entraînement + évaluation -> models/ et reports/
python seed_demo.py         # 6 patients de TEST + comptes de démo + clés d'appareil
python test_api.py          # 25 tests : login, autorisations, clé d'appareil, anti brute-force, replay live
python app.py               # plateforme sur http://localhost:5000  (dashboard + API)
```

## Architecture
`mesures montre -> POST /api/ingest -> features (common.py) -> détection RF + prédiction GB -> règle de décision -> SQLite -> dashboard médecin`

| Fichier | Rôle |
|---|---|
| `common.py` | features + baseline personnelle (identique en entraînement et en production) |
| `generate_data.py` | données mock : circadien, sport, bruit capteur, 5 scénarios (fièvre, tachycardie, hypoxie, hypertension, chute) |
| `train.py` | compare les modèles, évalue sur patients jamais vus, sauvegarde modèles + graphes |
| `pipeline.py` | inférence + décision (OK / REST / CONSULT_DOCTOR / ALERT_HOSPITAL) + raisons lisibles |
| `app.py` | API Flask + SQLite (readings, events, alerts) + backup |

## Endpoints
`POST /api/login` · `POST /api/logout` · `GET /api/me` · `POST /api/patients` (médecin/admin) · `GET /api/patients` · `POST /api/ingest` (clé appareil) · `GET /api/patients/<id>/series?signals=hr,spo2&bucket=15` · `GET /api/patients/<id>/events` · `GET /api/alerts[?patient_id=]` · `POST /api/backup` (admin)

## Choix des modèles (réponses au jury)
- **Random Forest (détection)** : robuste au bruit capteur, capture les interactions entre signaux (FC haute + activité faible = anormal ; FC haute + sport = normal), explicable via `feature_importances_`. Meilleur que la régression logistique (F1 macro 0.92 vs 0.84) et que les seuils fixes.
- **Gradient Boosting (prédiction à 15 min)** : modélise l'évolution (pentes, tendances) ; sortie = probabilité d'urgence imminente.
- **Isolation Forest** : testé comme détecteur d'anomalie personnalisé, AUC 0.62 → **rejeté** ; remplacé par l'écart à la baseline personnelle (z-score), plus simple et explicable.
- **Métrique principale = recall de la classe "urgence"** : rater une urgence est plus grave qu'une fausse alerte.
- **Split par patient** (pas par ligne) pour éviter la fuite de données.

## Limites à assumer
- Données **synthétiques** : les scores prouvent que le pipeline fonctionne, pas la performance clinique. Phase 2 : données réelles + validation médicale.
- Prédiction à 15 min : précision faible (≈22 %), rappel ≈59 % ; elle ne déclenche qu'un conseil de consultation, jamais l'alerte hôpital. Les chutes sont imprévisibles.
- Une même urgence peut déclencher plusieurs alertes (fragmentation) : ajouter un délai de blocage (cooldown) avant la production.
- La tension mesurée au poignet sans brassard est peu fiable en réel : à valider matériellement.
- Envoi d'alerte, hôpital le plus proche, authentification médecin/patient : **mock / à implémenter**.
- Dispositif médical : réglementation (marquage CE / MDR) à prévoir pour une vraie commercialisation.

## Comptes et sécurité
- Comptes de **démo** (mot de passe `demo-1234-Change!`, ou variable `DEMO_PASSWORD`) : `admin`, `dr.salah` (patients 1-3), `dr.mariem` (patients 4-6), `p005` (patient). À changer en production.
- Rôles : **patient** = ses données seulement ; **médecin** = ses patients assignés ; **admin** = tout + backup.
- La montre n'utilise pas de session : elle envoie une **clé d'appareil** (`X-Device-Key`), générée à la création du patient et affichée une seule fois (stockée hachée).
- Mots de passe hachés (werkzeug), 8 caractères minimum, blocage 5 min après 5 échecs, cookie de session HttpOnly + SameSite=Lax, en-têtes CSP / nosniff.
- À faire avant la production : HTTPS (variable `HTTPS=1` pour le cookie Secure), `SECRET_KEY` en variable d'environnement, limitation de débit partagée (Redis), journal d'audit des accès médecin, conformité des données de santé (consentement, RGPD / loi tunisienne sur les données personnelles).
