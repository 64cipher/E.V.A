# E.V.A
Enhanced Voice Assistant

# EVA – Enhanced Voice Assistant

![eva_054704](https://github.com/user-attachments/assets/5ef974ad-4d9c-46da-832e-e7bf9b48a514)


## Présentation

EVA (Enhanced Voice Assistant) est un assistant personnel vocal et textuel écrit en Python 🔥. Il combine les capacités du modèle **Gemini** de Google, l’API Google Maps, les services Gmail/Calendar/Tasks, SerpAPI pour la recherche Web, et OpenWeatherMap pour la météo, le tout sous une seule interface Web réactive basée sur [Tailwind CSS](https://tailwindcss.com/).

**Use‑case principal :** un hub productivité « tout‑en‑un » piloté à la voix : créer des événements calendrier, envoyer des e‑mails, obtenir un itinéraire, lancer une recherche Web, gérer contacts & tâches… et obtenir la réponse parlée.

---

## Fonctionnalités clés

| Catégorie         | Détail                                                                        |
| ----------------- | ----------------------------------------------------------------------------- |
| **NLP/IA**        | Appels direct au modèle Gemini 2 (configurable).                              |
| **Voix**          | 🔈 Synthèse vocale via gTTS (facultatif) & Web Speech API côté navigateur.    |
| **Google API**    | OAuth 2 offline + Calendar, Gmail, Tasks, Maps Directions.                    |
| **Recherche Web** | Résumés SerpAPI (fallback answer‑box / knowledge graph).                      |
| **Météo**         | OpenWeatherMap affiché dans le tableau de bord.                               |
| **Contact book**  | Carnet d’adresses local (JSON).                                               |
| **WebSocket**     | Dialogue temps‑réel entre front (HTML/JS) et backend (Flask + Flask‑Sock).    |
| **Interface**     | Panneau latéral (carte, recherche, e‑mails, tâches, calendrier, code généré). |

---

## Architecture rapide

```
┌───────────────┐            WebSocket              ┌──────────────┐
│   Front‑end   │  <─────────────────────────────►  │   Flask API  │
│  index.html   │         (JSON + audio)            │   main.py    │
└───────────────┘                                   └──────────────┘
        │                                                    │
        ▼ Google Maps JS                                     ▼
   Browser APIs : Speech‑to‑Text, gTTS audio          Google APIs / Gemini / SerpAPI
```

---

## Prérequis

* **Python ≥ 3.10**
* Un navigateur moderne (Chrome/Edge/Brave ≥ v113 pour l’API SpeechRecognition)
* Clés/API :

  * Google Gemini `GEMINI_API_KEY`
  * Google Maps JS `GOOGLE_MAPS_API_KEY`
  * Google OAuth 2 credentials (`client_secret.json`)
  * SerpAPI `SERPAPI_API_KEY` (optionnel mais recommandé)
  * OpenWeatherMap `OPENWEATHERMAP_API_KEY` (frontend)
* `ffmpeg` installé (optionnel : synthèse gTTS fiable)

---

## Installation rapide (5 minutes)

1. **Clone + virtualenv**

   ```bash
   git clone https://github.com/<votre‑user>/eva-assistant.git
   cd eva-assistant
   python -m venv .venv && source .venv/bin/activate  # Windows : .venv\Scripts\activate
   ```
2. **Dépendances Python**

   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt  # fourni dans le repo
   ```
3. \*\*Fichier \*\***`.env`** (à la racine) :

   ```dotenv
   GEMINI_API_KEY=sk‑...
   GEMINI_MODEL_NAME=gemini-2.0-flash          # facultatif
   GOOGLE_MAPS_API_KEY=AIza...
   SERPAPI_API_KEY=...
   FLASK_SECRET_KEY=change‑me-super‑secret
   GOOGLE_CLIENT_SECRETS_FILE=client_secret.json
   # Facultatif : décommenter si besoin de proxy
   # HTTP_PROXY=http://...
   # HTTPS_PROXY=https://...
   ```
4. **OAuth Google**

   * Allez sur [console.cloud.google.com](https://console.cloud.google.com)
   * Créez un projet ▶ “API & Services” ▶ “Identifiants” ▶ **“ID client OAuth 2.0 (Desktop)”**.
   * Téléchargez `client_secret_<id>.json`, renommez‑le `client_secret.json`, placez‑le à la racine.
   * Dans l’écran de consentement, ajoutez `http://localhost:5000/oauth2callback_google` comme URI de redirection.
5. **Frontend : insérez vos clés JS**

   * Ouvrez `index.html` et recherchez :

     ```html
     <script async defer src="https://maps.googleapis.com/maps/api/js?key=GOOGLE_MAPS_API_KEY&callback=initMap&libraries=places"></script>
     ```

     Remplacez `GOOGLE_MAPS_API_KEY` par la clé réelle.
   * Dans le JS (ligne \~3000), remplacez `const apiKey = 'OPENWEATHERMAP_API_KEY'` par votre clé OpenWeatherMap.
6. **Lancer le backend**

   ```bash
   python main.py              # écoute sur http://localhost:5000
   ```
7. **Servir le frontend** (au choix)

   * Mode rapide :

     ```bash
     python -m http.server 8080 --bind 127.0.0.1
     ```

     puis ouvrez [http://localhost:8080/index.html](http://localhost:8080/index.html)
   * Ou via une extension Live Server (VS Code) ou Nginx.
8. **Autoriser Google**

   * Dans l’UI EVA cliquez sur **“Autoriser l’accès aux services Google”** puis connectez‑vous.

Ça y est ! Parlez ou tapez votre requête dans EVA 👾.

---

## Utilisation

* **Voix continue** : appuyez sur **Espace** pour commencer, Space à nouveau pour arrêter.
* **Voix ponctuelle** : cliquez sur le micro.
* **Commandes supportées** : « Crée un événement demain à 14 h », « Envoie un e‑mail à Alice … », « Ajoute une tâche … », « Itinéraire jusqu’à Genève », « Recherche Web : flux d’énergie libre ».
* EVA détecte une commande ➜ renvoie un JSON (voir `SYSTEM_MESSAGE_CONTENT` dans `main.py`) ➜ backend exécute.

---

## Dépendances principales

```text
Flask
Flask‑Sock
Flask-CORS
python‑dotenv
google‑auth‑oauthlib
google‑api‑python‑client
googlemaps
gtts
pillow
simple‑websocket
serpapi
google‑generativeai
pickle
dotenv
```

Générez le fichier exact via :

```bash
pip freeze > requirements.txt
```

---

## Variables d’environnement détaillées

| Variable                     | Description                               | Obligatoire        |
| ---------------------------- | ----------------------------------------- | ------------------ |
| `GEMINI_API_KEY`             | Clé API Gemini v2                         | ✔︎                 |
| `GEMINI_MODEL_NAME`          | Nom du modèle (défaut : gemini‑2.0‑flash) | ❌                  |
| `GOOGLE_MAPS_API_KEY`        | Clé JS Google Maps (itinéraires + carte)  | ❌ (désactive map)  |
| `SERPAPI_API_KEY`            | Clé SerpAPI pour la recherche Web         | ❌ (web search off) |
| `FLASK_SECRET_KEY`           | Secret session Flask                      | ✔︎                 |
| `GOOGLE_CLIENT_SECRETS_FILE` | Nom du fichier JSON OAuth                 | ✔︎                 |
| `OPENWEATHERMAP_API_KEY`     | Clé météo (frontend)                      | ❌ (pas de météo)   |

---

## Scripts utiles

| Action               | Commande                     |
| -------------------- | ---------------------------- |
| Lancer backend (dev) | `python main.py`             |
| Linter (ruff)        | `ruff check .`               |
| Formatage (black)    | `black .`                    |
| Frontend rapide      | `python -m http.server 8080` |

---

## Sécurité

* **Ne laissez jamais** votre vraie clé Gemini ou Google dans le repo public.
* Ajoutez `client_secret.json` et `.env` dans `.gitignore` avant de pousser.
* Le code force `OAUTHLIB_INSECURE_TRANSPORT=1` pour le dev local ➜ **Ne pas utiliser en production**.

---
