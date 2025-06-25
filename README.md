# E.V.A – Evolved Virtual Assistant avec Mode Agent (Expérimental)

Serveur Flask + Web UI - NodeJS, NGINX, Python, etc... Au choix.

Python3.11 requis.

Inspiré par le projet ada_app de Nlouis38
https://github.com/Nlouis38/ada 

Merci à lui pour son travail.

![image](https://github.com/user-attachments/assets/ccce730b-8ad0-4279-962d-2b041622112d)


![video](https://cdn.discordapp.com/attachments/1276932912859844773/1387251334901796914/2025-06-25_03-58-31.mp4)

## Présentation

EVA (Evolved Virtual Assistant) est un assistant personnel vocal et textuel français écrit en Python. Il combine les capacités du modèle **Gemini** de Google, l’API Google Maps, les services Gmail/Calendar/Tasks, Custom Search API pour la recherche Web, et OpenWeatherMap pour la météo, le tout sous une seule interface Web réactive basée sur [Tailwind CSS](https://tailwindcss.com/).

Le mode Agent est très couteux en ressource sur API, donc faites attention.

**Use‑case principal :** un hub productivité « tout‑en‑un » piloté à la voix : créer des événements calendrier, envoyer des e‑mails, obtenir un itinéraire, lancer une recherche Web, gérer contacts & tâches… et obtenir la réponse parlée.

---

## Fonctionnalités clés

| Catégorie         | Détail                                                                        |
| ----------------- | ----------------------------------------------------------------------------- |
| **NLP/IA**        | Appels direct au modèle Gemini 2 (configurable).                              |
| **Voix**          | Synthèse vocale via gTTS (facultatif) & Web Speech API côté navigateur.       |
| **Google API**    | OAuth 2 offline + Calendar, Gmail, Tasks, Maps Directions.                    |
| **Recherche Web** | Résumés API (fallback answer‑box / knowledge graph).                          |
| **Météo**         | OpenWeatherMap affiché dans le tableau de bord.                               |
| **Contact book**  | Carnet d’adresses local (JSON).                                               |
| **WebSocket**     | Dialogue temps‑réel entre front (HTML/JS) et backend (Flask + Flask‑Sock).    |
| **Interface**     | Panneau latéral (carte, recherche, e‑mails, tâches, calendrier, code généré). |
| **Transcript Audio Whisper**  | Convertisserz un audio MP3 ou WAV en texte.                       |
| **Visualiseur 3D**     | Demandez à E.V.A de créer un objet comme un cube, une sphere, un cône ou un tore en 3D.    |
| **Execution de code** | E.V.A peut executer du code python et intéragir avec le shell            |
| **Mode Agent** | E.V.A peut executer des tâches en plusieurs étapes                               |
| **Comptibilité MIDI** | E.V.A peut jouer des notes de musique sur votre DAW comme FL Studio (nécessite LoopMIDI) |
---

## Architecture rapide

```
┌───────────────┐            WebSocket              ┌──────────────┐
│   Front‑end   │  <─────────────────────────────►  │   Flask API  │
│  index.html   │         (JSON + audio)            │   main.py    │
└───────────────┘                                   └──────────────┘
        │                                                    │
        ▼ Google Maps JS                                     ▼
   Browser APIs : Speech‑to‑Text, gTTS audio          Google APIs / Gemini / Custom Search API
```

---

## Prérequis

* **Python ≥ 3.10**
* Un navigateur moderne (Chrome/Edge/Brave ≥ v113 pour l’API SpeechRecognition)
* Clés/API :

  * Google Gemini `GEMINI_API_KEY`
  * Google Maps JS `GOOGLE_MAPS_API_KEY`
  * Google OAuth 2 credentials (`client_secret.json`)
  * Google Custom Search `GOOGLE_CUSTOM_SEARCH_API_KEY` et le CX `GOOGLE_CUSTOM_SEARCH_CX` (optionnel mais recommandé)
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
   pip install -r requirements.txt
   ```
3. \*\*Fichier \*\***`.env`** (à la racine) :

   ```dotenv
   GEMINI_API_KEY=sk‑...
   GEMINI_MODEL_NAME=gemini-2.0-flash          # facultatif
   GOOGLE_MAPS_API_KEY=AIza...
   GOOGLE_CUSTOM_SEARCH_API_KEY==...
   GOOGLE_CUSTOM_SEARCH_CX=YOUR_CX_KEY
   FLASK_SECRET_KEY=change‑me-super‑secret
   GOOGLE_CLIENT_SECRETS_FILE=client_secret.json
   # Facultatif : décommenter si besoin de proxy
   # HTTP_PROXY=http://...
   # HTTPS_PROXY=https://...
   ```
4. **OAuth Google et AI Studio**

   * Allez sur [console.cloud.google.com](https://console.cloud.google.com)
   * Créez un projet ▶ “API & Services” ▶ “Identifiants” ▶ **“ID client OAuth 2.0 (Desktop)”**.
   * Dans l’écran de consentement, ajoutez `http://localhost:5000/oauth2callback_google` comme URI de redirection.

   ![image](https://github.com/user-attachments/assets/b9303036-4940-4d35-a052-3caac4190b03)

   * Téléchargez `client_secret_<id>.json`, renommez‑le `client_secret.json`, placez‑le à la racine.

   ![Capture d’écran 2025-05-21 123055](https://github.com/user-attachments/assets/6529a5c5-5dd6-4642-b71a-1c37640e3753)

   * Récupérez et utilisez gratuitement votre clé API Gemini sans compte de facturation sur [AI Studio](https://aistudio.google.com)
     (Vous pouvez activer la facturation pour gemini-2.0-flash pour pas cher : 0.10$/M de tokens INPUT et 0.50$/M de tokens en OUTPUT en cas d'utilise plus intensive d'E.V.A)

     ![image](https://github.com/user-attachments/assets/a29bbfaa-dd6f-4fc3-93be-bc27c35fc48b)

   * Générer une clé api [OpenWeatherMap](https://openweathermap.org/api)

     ![image](https://github.com/user-attachments/assets/c3dac442-f003-4edc-be9c-920e132419ed)

   * Activez Directions API pour afficher les itinéraires sur la map dans "API et service" de Console Cloud.

     ![image](https://github.com/user-attachments/assets/653019d5-3db4-4e6e-86ea-08345b6055b1)

     ![image](https://github.com/user-attachments/assets/83ba0604-9069-4685-ab57-1bb913b8f329)

     ![image](https://github.com/user-attachments/assets/a2c8d592-d9d9-4d88-9647-3a59a97a0261)

   * Pour Google Custom Search API, vous devez aller sur [La plate-forme de moteur de recherche personnalisé](https://programmablesearchengine.google.com/)

     ![image](https://github.com/user-attachments/assets/bc5271b2-0d62-4632-bbf8-ca34b65a34d2)

     Copier l'ID du moteur de recherche et coller le dans `GOOGLE_CUSTOM_SEARCH_CX` présent dans le fichier .env  
   
     ![image](https://github.com/user-attachments/assets/ed6a61d3-f303-46ba-8e17-b190fb8597a1)

 
     
6. **Frontend : insérez vos clés JS**

   * Ouvrez `index.html` et recherchez, ligne 9 :

     ```html
     <script async defer src="https://maps.googleapis.com/maps/api/js?key=GOOGLE_MAPS_API_KEY&callback=initMap&libraries=places"></script> 
     ```

     Remplacez `GOOGLE_MAPS_API_KEY` par la clé réelle.
   * Ligne 584, remplacez `const openWeatherMapApiKey = 'YOUR_OPENWEATHERMAP_API_KEY';` par votre clé OpenWeatherMap.
7. **Lancer le backend**

   ```bash
   python main.py              # écoute sur http://localhost:5000
   ```
8. **Servir le frontend** (au choix)

   * Mode rapide :

     ```bash
     python -m http.server 8080 --bind 127.0.0.1
     ```

     puis ouvrez [http://localhost:8080/index.html](http://localhost:8080/index.html)
   * Ou via une extension Live Server (VS Code), Nginx ou NodeJS.

     
9. **Autoriser Google**

   * Dans l’UI EVA cliquez sur **“Autoriser l’accès aux services Google”** puis connectez‑vous.

Ça y est ! Parlez ou tapez votre requête dans EVA 👾.

*⚠️ Si la map ne charge pas, appuyez sur CTRL+F5*

---

N'hésitez pas à rentrer des informations selon votre situation pro/perso pour donner du contexte dans `SYSTEM_MESSAGE_CONTENT`

Ligne 435:
```L'utilisateur s'appelle 'VOTRE_PRENOM'.```

Ligne 457:
```par exemple : 'En route pour {destination}, VOTRE_PRENOM```

---

## Utilisation et fonctionnalités

* **Voix continue** : appuyez sur **Espace** pour commencer, Space à nouveau pour arrêter.
* **Voix ponctuelle** : cliquez sur le micro.
* **Mode interruption** : Voix continu avec la possibilité d'interrompre E.V.A en parlant dans le micro.
* **Envoi de fichiers supporté** : jpg, png, doc et txt
* **Commandes supportées** : « Crée un événement demain à 14 h », « Envoie un e‑mail à Alice … », « Ajoute une tâche … », « Itinéraire jusqu’à Paris », « Recherche Web : les actus sur l'IA ».
* **"OK Eva"** : Vous pouvez déclancher l'écoute par cette simple phrase.
* **Lancement d'applications** : E.V.A peux ouvrir des applications de votre PC. Configurez les chemins d'accès dans ```.env``` avec les variables ```APP_NOM_DE_L'APP_PATH="C:\chemin\vers\app.exe```

EVA détecte une commande ➜ renvoie un JSON (voir `SYSTEM_MESSAGE_CONTENT` dans `main.py`) ➜ backend exécute.

* **Raccourcis touches** : Caméra 'C' - Muet 'M' - Mode Interruption 'I' 
---

## Dépendances principales

```text
requests
flask
flask‑sock
flask-cors
google‑auth‑oauthlib
google‑api‑python‑client
google-auth-httplib2
googlemaps
gtts
pillow
simple‑websocket
google‑generativeai
dotenv
google-search-results
beautifulsoup4
openai-whisper
ffmpeg-python
pyvista
spotipy
mido
PyPDF2
rtmidi-python
yt-dlp
```

Générez le fichier exact via :

```bash
pip freeze > requirements.txt
```

---

## Variables d’environnement détaillées

| Variable                                             | Description                               | Obligatoire        |
| -----------------------------------------------------| ----------------------------------------- | ------------------ |
| `GEMINI_API_KEY`                                     | Clé API Gemini v2                         | ✔︎                 |
| `GEMINI_MODEL_NAME`                                  | Nom du modèle (défaut : gemini‑2.0‑flash) | ❌                  |
| `GOOGLE_MAPS_API_KEY`                                | Clé JS Google Maps (itinéraires + carte)  | ❌ (désactive map)  |
| `CUSTOM_SEARCH_API_KEY` et `GOOGLE_CUSTOM_SEARCH_CX` | Clé Custom Search pour la recherche Web   | ❌ (web search off) |
| `FLASK_SECRET_KEY`                                   | Secret session Flask                      | ✔︎                 |
| `GOOGLE_CLIENT_SECRETS_FILE`                         | Nom du fichier JSON OAuth                 | ✔︎                 |
| `OPENWEATHERMAP_API_KEY`                             | Clé météo (frontend)                      | ❌ (pas de météo)   |

---

## Scripts utiles

| Action               | Commande                     |
| -------------------- | ---------------------------- |
| Lancer backend (dev) | `python main.py`             |
| Linter (ruff)        | `ruff check .`               |
| Formatage (black)    | `black .`                    |
| Frontend rapide      | `python -m http.server 8080` |

---
