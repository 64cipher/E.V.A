# Importation des bibliothèques nécessaires
import os
import io
import sys
import base64
import traceback
import re
import pickle # Pour stocker les tokens OAuth (exemple simple)
import datetime # Pour l'exemple avec Google Calendar
from email.mime.text import MIMEText # Pour créer le corps de l'e-mail
import json # Ajouté pour WebSockets et carnet d'adresses
import time

# --- Configuration Initiale (Chargement .env AVANT tout le reste) ---
from dotenv import load_dotenv
load_dotenv()
# print("DEBUG: Fichier .env chargé (si existant).")

# !!!!! ATTENTION : POUR DÉVELOPPEMENT LOCAL UNIQUEMENT !!!!!
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
print("ATTENTION: OAUTHLIB_INSECURE_TRANSPORT activé. Pour développement local uniquement.")
# !!!!! FIN DE L'AVERTISSEMENT !!!!!


# --- gTTS Configuration ---
gtts_enabled = False
print("--- Début Configuration gTTS ---")
try:
    from gtts import gTTS
    # print("DEBUG: Importation gTTS réussie.")
    gtts_enabled = True
except ImportError:
    print("ERREUR CRITIQUE: Bibliothèque 'gTTS' non trouvée. Pour l'installer: pip install gTTS")
    print("Synthèse vocale avec gTTS désactivée.")
print("--- Fin Configuration gTTS ---")

# --- Autres Importations (Flask, Pillow, etc.) ---
from flask import Flask, request, jsonify, redirect, session, url_for
from flask_cors import CORS
from PIL import Image
from flask_sock import Sock

# --- Imports pour Google OAuth et API Client ---
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError

# --- Import pour SerpAPI (Recherche Web) ---
serpapi_client_available = False
try:
    from serpapi import GoogleSearch
    serpapi_client_available = True
    # print("DEBUG: Bibliothèque SerpAPI 'google-search-results' trouvée et importée.")
except ImportError:
    print("AVERTISSEMENT: Bibliothèque SerpAPI 'google-search-results' NON TROUVÉE.")
    print("             Pour l'installer, exécutez: pip install google-search-results")
    print("             La fonctionnalité de recherche web sera DÉSACTIVÉE.")

from simple_websocket.errors import ConnectionClosed


# Récupérer les clés API et configurations
gemini_api_key = os.getenv("GEMINI_API_KEY")
google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY")
serpapi_api_key = os.getenv("SERPAPI_API_KEY")
gemini_model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash") # Modèle par défaut si non spécifié

if not gemini_api_key:
    print("Erreur critique: Clé API Gemini manquante. Arrêt.")
    sys.exit()

if not google_maps_api_key:
    print("AVERTISSEMENT: Clé API Google Maps (GOOGLE_MAPS_API_KEY) manquante dans le fichier .env.")
    print("             La fonctionnalité d'itinéraire sera DÉSACTIVÉE.")

if serpapi_client_available:
    if not serpapi_api_key:
        print("AVERTISSEMENT: Clé API SerpAPI (SERPAPI_API_KEY) manquante dans le fichier .env.")
        print("             La recherche web sera DÉSACTIVÉE.")
        serpapi_client_available = False
    # else:
        # print("DEBUG: Clé API SerpAPI trouvée.")
else:
    print("INFO: Recherche web SerpAPI non disponible car la bibliothèque n'a pas pu être importée.")


app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": ["http://127.0.0.1:8080", "http://localhost:8080"]}}, supports_credentials=True)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "une_cle_secrete_par_defaut_tres_forte")
sock = Sock(app)

CLIENT_SECRETS_FILE = os.getenv("GOOGLE_CLIENT_SECRETS_FILE", "client_secret.json")
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/tasks',
]
TOKEN_PICKLE_FILE = 'token.pickle'

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
CONTACTS_FILE = os.path.join(BASE_DIR, 'contacts.json')
# print(f"DEBUG: Chemin absolu pour contacts.json: {CONTACTS_FILE}")

# Variable globale pour le carnet d'adresses
CONTACT_BOOK = {}

# Dictionnaire pour la conversion des mois français en numéros
MONTH_FR_TO_NUM = {
    'janvier': 1, 'février': 2, 'fevrier': 2, 'mars': 3, 'avril': 4, 'mai': 5, 'juin': 6,
    'juillet': 7, 'août': 8, 'aout': 8, 'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12
}

# --- Fonctions pour le carnet d'adresses ---
def load_contacts():
    global CONTACT_BOOK
    try:
        if not os.path.exists(CONTACTS_FILE):
            with open(CONTACTS_FILE, 'w', encoding='utf-8') as f:
                json.dump({}, f)
            CONTACT_BOOK = {}
            return
        with open(CONTACTS_FILE, 'r', encoding='utf-8') as f:
            file_content = f.read()
            if not file_content.strip():
                CONTACT_BOOK = {}
            else:
                f.seek(0)
                loaded_data = json.load(f)
                if isinstance(loaded_data, dict):
                    CONTACT_BOOK = loaded_data
                else:
                    print(f"AVERTISSEMENT [load_contacts]: Contenu de {CONTACTS_FILE} n'est pas un dictionnaire JSON. Reçu: {type(loaded_data)}. Initialisation vide.")
                    CONTACT_BOOK = {}
    except json.JSONDecodeError as e:
        print(f"ERREUR [load_contacts]: Décodage JSON échoué pour {CONTACTS_FILE}: {e}. CONTACT_BOOK réinitialisé.")
        CONTACT_BOOK = {}
    except Exception as e:
        print(f"ERREUR [load_contacts]: Erreur inattendue: {e}. CONTACT_BOOK réinitialisé.")
        traceback.print_exc()
        CONTACT_BOOK = {}

def save_contacts():
    global CONTACT_BOOK
    try:
        with open(CONTACTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(CONTACT_BOOK, f, indent=4, ensure_ascii=False)
        if os.path.exists(CONTACTS_FILE) and os.path.getsize(CONTACTS_FILE) < 2 and len(CONTACT_BOOK) > 0:
            print(f"AVERTISSEMENT [save_contacts]: Fichier {CONTACTS_FILE} semble vide après sauvegarde alors que CONTACT_BOOK n'est pas vide!")
        return True
    except Exception as e:
        print(f"ERREUR critique [save_contacts] lors de la sauvegarde dans {CONTACTS_FILE}: {e}")
        traceback.print_exc()
        return False

def add_contact_to_book(name, email):
    global CONTACT_BOOK
    normalized_name = name.lower().strip()
    email_addr = email.strip()
    if not normalized_name: return "Le nom du contact ne peut pas être vide."
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email_addr): return f"L'adresse e-mail '{email_addr}' ne semble pas valide."
    CONTACT_BOOK[normalized_name] = {"display_name": name, "email": email_addr}
    if save_contacts():
        load_contacts() # Recharger pour s'assurer de la cohérence
        if normalized_name in CONTACT_BOOK and CONTACT_BOOK[normalized_name]["email"] == email_addr:
            return f"Contact '{name}' ajouté avec l'email '{email_addr}'."
        else:
            print(f"AVERTISSEMENT [add_contact_to_book]: Échec de confirmation du contact '{normalized_name}' après rechargement. CONTACT_BOOK: {CONTACT_BOOK}")
            return f"Erreur de vérification après sauvegarde du contact '{name}'."
    else:
        load_contacts() 
        return f"Erreur lors de la sauvegarde du contact '{name}'."

def get_contact_email(name):
    global CONTACT_BOOK
    normalized_name = name.lower().strip()
    contact_info = CONTACT_BOOK.get(normalized_name)
    return contact_info["email"] if contact_info else None

def list_contacts_from_book():
    global CONTACT_BOOK
    if not CONTACT_BOOK: return "Votre carnet d'adresses est vide."
    # This function already returns a detailed list, which is fine for panel_data.
    # The chat message will be "Voici vos contacts."
    return "Voici vos contacts :\n" + "\n".join([f"- {c['display_name']} ({c['email']})" for c in CONTACT_BOOK.values()])

def remove_contact_from_book(name):
    global CONTACT_BOOK
    normalized_name = name.lower().strip()
    if normalized_name in CONTACT_BOOK:
        removed_contact_name = CONTACT_BOOK[normalized_name]["display_name"]
        del CONTACT_BOOK[normalized_name]
        if save_contacts():
            load_contacts()
            if normalized_name not in CONTACT_BOOK:
                return f"Contact '{removed_contact_name}' supprimé."
            else:
                print(f"AVERTISSEMENT [remove_contact_from_book]: Contact '{removed_contact_name}' toujours présent après rechargement.")
                return f"Erreur de confirmation de suppression pour '{removed_contact_name}'."
        else:
            load_contacts()
            return f"Erreur de sauvegarde après suppression du contact '{removed_contact_name}'."
    return f"Contact '{name}' non trouvé."

load_contacts()

# --- Fonctions Google Calendar ---
def parse_french_datetime(datetime_str):
    # print(f"DEBUG [parse_french_datetime] Parsing: '{datetime_str}'")
    now = datetime.datetime.now()
    datetime_str_cleaned = datetime_str.strip() # Nettoyer les espaces au début/fin

    if "demain" in datetime_str_cleaned.lower():
        target_date = now + datetime.timedelta(days=1)
        time_part_match = re.search(r"(\d{1,2})h(?:(\d{2}))?", datetime_str_cleaned, re.IGNORECASE)
        if time_part_match:
            hour = int(time_part_match.group(1))
            minute = int(time_part_match.group(2)) if time_part_match.group(2) else 0
            return target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return target_date.replace(hour=9, minute=0, second=0, microsecond=0) 

    if "aujourd'hui" in datetime_str_cleaned.lower() or "ce jour" in datetime_str_cleaned.lower():
        target_date = now
        time_part_match = re.search(r"(\d{1,2})h(?:(\d{2}))?", datetime_str_cleaned, re.IGNORECASE)
        if time_part_match:
            hour = int(time_part_match.group(1))
            minute = int(time_part_match.group(2)) if time_part_match.group(2) else 0
            return target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return target_date.replace(hour=now.hour, minute=now.minute, second=0, microsecond=0)

    # Regex pour date ET heure, avec "le" optionnel
    pattern_datetime = re.compile(
        r"(?:le\s+|l')?(\d{1,2})\s+(Janvier|Février|Fevrier|Mars|Avril|Mai|Juin|Juillet|Août|Aout|Septembre|Octobre|Novembre|Décembre)\s*(?:l'année\s*(\d{4})\s*)?(?:à|a)\s*(\d{1,2})h(?:(\d{2}))?",
        re.IGNORECASE
    )
    match_datetime = pattern_datetime.match(datetime_str_cleaned)

    if match_datetime:
        day_str, month_name_fr, year_str, hour_str, minute_str = match_datetime.groups()
    else:
        # Regex pour date SEULEMENT, avec "le" optionnel
        pattern_date_only = re.compile(
             r"(?:le\s+|l')?(\d{1,2})\s+(Janvier|Février|Fevrier|Mars|Avril|Mai|Juin|Juillet|Août|Aout|Septembre|Octobre|Novembre|Décembre)\s*(?:l'année\s*(\d{4})\s*)?",
             re.IGNORECASE
        )
        match_date_only = pattern_date_only.match(datetime_str_cleaned)
        if match_date_only:
            day_str, month_name_fr, year_str = match_date_only.groups()
            hour_str, minute_str = "9", "00" # Heure par défaut si seulement la date est fournie
        else:
            # print(f"DEBUG [parse_french_datetime] No match found for: '{datetime_str_cleaned}'")
            return None # Aucun format reconnu

    try:
        day = int(day_str)
        month_num = MONTH_FR_TO_NUM.get(month_name_fr.lower())
        if not month_num:
            # print(f"DEBUG [parse_french_datetime] Mois non reconnu: '{month_name_fr}'")
            return None
        year = int(year_str) if year_str else datetime.datetime.now().year
        hour = int(hour_str)
        minute = int(minute_str) if minute_str else 0 
        if not (1 <= day <= 31 and 0 <= hour <= 23 and 0 <= minute <= 59):
            # print(f"DEBUG [parse_french_datetime] Valeurs jour/heure/minute invalides: D={day}, H={hour}, M={minute}")
            return None
        # print(f"DEBUG [parse_french_datetime] Parsed: Y={year}, M={month_num}, D={day}, H={hour}, Min={minute}")
        return datetime.datetime(year, month_num, day, hour, minute)
    except ValueError:
        # print(f"DEBUG [parse_french_datetime] ValueError lors de la conversion int.")
        return None
    except Exception as e:
        # print(f"DEBUG [parse_french_datetime] Erreur inattendue: {e}")
        traceback.print_exc()
        return None

def create_calendar_event(summary, start_datetime_obj, duration_hours=1):
    creds = get_google_credentials()
    if not creds:
        return "Authentification Google requise pour ajouter des événements au calendrier. Veuillez autoriser via /authorize_google."

    if not summary or not summary.strip():
        return "Le titre de l'événement ne peut pas être vide."
    if not isinstance(start_datetime_obj, datetime.datetime):
        return "Date et heure de début invalides pour l'événement."

    end_datetime_obj = start_datetime_obj + datetime.timedelta(hours=duration_hours)

    event_body = {
        'summary': summary,
        'start': {'dateTime': start_datetime_obj.isoformat(), 'timeZone': 'Europe/Paris'},
        'end': {'dateTime': end_datetime_obj.isoformat(), 'timeZone': 'Europe/Paris'},
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'popup', 'minutes': 30},
                {'method': 'popup', 'minutes': 10}
            ],
        },
    }
    try:
        service = build('calendar', 'v3', credentials=creds)
        created_event = service.events().insert(calendarId='primary', body=event_body).execute()
        event_link = created_event.get('htmlLink', 'Lien non disponible')
        # This is a confirmation message, not a list for the panel.
        return f"Événement '{summary}' ajouté à votre calendrier pour le {start_datetime_obj.strftime('%d %B %Y à %Hh%M')}. Lien: {event_link}"
    except HttpError as error:
        error_content = error.content.decode('utf-8') if error.content else "Aucun détail d'erreur."
        print(f"Erreur API Calendar (création événement): Status={error.resp.status}, Raison={error.resp.reason}, Détails={error_content}")
        if error.resp.status == 401 or 'invalid_grant' in str(error).lower():
            if os.path.exists(TOKEN_PICKLE_FILE): os.remove(TOKEN_PICKLE_FILE)
            return "Identifiants Calendar invalides/révoqués. Réauthentifiez-vous."
        return f"Erreur lors de la création de l'événement ({error.resp.status}): {error_content}"
    except Exception as e:
        print(f"Erreur inattendue Calendar (création événement): {e}")
        traceback.print_exc()
        return f"Erreur inattendue lors de la création de l'événement: {type(e).__name__}"


SYSTEM_MESSAGE_CONTENT = """
Tu es EVA (Enhanced Voice Assistant), une intelligence artificielle sophistiquée, conçue pour être un assistant personnel polyvalent.
Ta tâche principale est d'analyser la requête de l'utilisateur.

Si la requête semble être une COMMANDE pour effectuer une action spécifique (comme ajouter un événement au calendrier, envoyer un email, chercher sur le web, obtenir un itinéraire, gérer des contacts, créer ou lister des tâches, lister des emails ou des événements de calendrier, ou obtenir les prévisions météo), tu DOIS la reformuler en un objet JSON structuré.
Le JSON doit avoir une clé "action" (valeurs possibles: "create_calendar_event", "list_calendar_events", "send_email", "list_emails", "create_task", "list_tasks", "add_contact", "list_contacts", "remove_contact", "get_contact_email", "get_directions", "web_search", "get_weather_forecast") et une clé "entities" contenant les informations extraites pertinentes pour cette action.

Exemples d'entités attendues pour chaque action :
- "create_calendar_event": {"summary": "titre de l'événement", "datetime_str": "description de la date et l'heure comme 'demain à 14h' ou 'le 25 décembre 2025 à 10h30'"}
- "list_calendar_events": {} (les entités peuvent être vides)
- "send_email": {"recipient_name_or_email": "nom du contact ou adresse email", "subject": "objet de l'email (peut être 'Sans objet')", "body": "contenu du message"}
- "list_emails": {} (les entités peuvent être vides)
- "create_task": {"title": "titre de la tâche", "notes": "notes additionnelles pour la tâche (optionnel)"}
- "list_tasks": {} (les entités peuvent être vides)
- "add_contact": {"name": "nom du contact", "email": "adresse email du contact"}
- "list_contacts": {} (les entités peuvent être vides)
- "remove_contact": {"name": "nom du contact à supprimer"}
- "get_contact_email": {"name": "nom du contact dont on veut l'email"}
- "get_directions": {"origin": "lieu de départ (optionnel, défaut Thonon-les-Bains si non spécifié par l'utilisateur)", "destination": "lieu d'arrivée"}
- "web_search": {"query": "la question ou les termes à rechercher"}
- "get_weather_forecast": {} (les entités sont vides, la localisation est gérée côté client)

Si une information essentielle pour une entité de commande est manquante (ex: pas de destination pour un itinéraire), essaie de la demander implicitement dans ta réponse JSON si possible, ou omets l'entité si elle est optionnelle. Si l'entité est cruciale et manquante, tu peux générer une action "clarify_command" avec les détails.

Si la requête est une QUESTION GÉNÉRALE, une salutation, ou une conversation qui NE correspond PAS à une commande spécifique listée ci-dessus, tu DOIS répondre directement en langage naturel. NE PAS générer de JSON dans ce cas. Ta réponse textuelle sera directement utilisée.

Si l'utilisateur fournit une image, analyse-la et intègre tes observations dans ta réponse si c'est pertinent pour une réponse générale. Pour les commandes, l'image n'est généralement pas utilisée.
Tu t'exprimes toujours en français, de manière claire, concise et professionnelle, tout en restant amicale.
N'écris jamais d'émojis. Écris des markdown quand on te demande du code informatique.
Les fonctionnalités pour Google Keep ne sont pas disponibles (informe l'utilisateur si demandé).
Le système principal (Python) gère l'authentification Google et l'appel aux API Google (Calendar, Gmail, Tasks, Maps) et SerpAPI.
Le système principal gère un carnet d'adresses local.
L'origine par défaut pour les itinéraires est "Thonon-les-Bains" si non spécifiée par l'utilisateur.
Les prévisions météo sont gérées par le client (JavaScript) en utilisant la localisation de l'utilisateur.
"""

import google.generativeai as genai
generative_model = None
try:
    genai.configure(api_key=gemini_api_key)
    generative_model = genai.GenerativeModel(
        model_name=gemini_model_name,
        system_instruction=SYSTEM_MESSAGE_CONTENT
    )
    print(f"Modèle Gemini chargé : {gemini_model_name} avec instruction système.")
except Exception as e:
    print(f"Erreur lors de la configuration du client Gemini : {e}")
    print("Le backend continuera sans le client Gemini.")

gemini_conversation_history = []
MAX_HISTORY_ITEMS = 10 

def get_google_credentials():
    creds = None
    if os.path.exists(TOKEN_PICKLE_FILE):
        with open(TOKEN_PICKLE_FILE, 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Erreur lors du rafraîchissement des tokens: {e}. L'utilisateur devra se réauthentifier.")
                if os.path.exists(TOKEN_PICKLE_FILE):
                    os.remove(TOKEN_PICKLE_FILE)
                return None
        else:
            return None
    if creds:
         with open(TOKEN_PICKLE_FILE, 'wb') as token_file: # Save refreshed token
            pickle.dump(creds, token_file)
    return creds

@app.route('/authorize_google')
def authorize_google():
    if not os.path.exists(CLIENT_SECRETS_FILE):
        return jsonify({"error": f"Fichier {CLIENT_SECRETS_FILE} non trouvé."}), 500
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for('oauth2callback_google', _external=True)
    )
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        prompt='consent' 
    )
    session['oauth_state'] = state
    return redirect(authorization_url)

@app.route('/oauth2callback_google')
def oauth2callback_google():
    state = session.pop('oauth_state', None)
    if not state or state != request.args.get('state'):
        print(f"ERREUR: État OAuth invalide. Attendu: {state}, Reçu: {request.args.get('state')}")
        return jsonify({"error": "Invalid OAuth state."}), 400

    if 'error' in request.args:
        error_message = request.args.get('error_description', request.args['error'])
        print(f"ERREUR d'autorisation Google: {error_message}")
        return jsonify({"error": f"Erreur d'autorisation Google: {error_message}"}), 400

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=state,
        redirect_uri=url_for('oauth2callback_google', _external=True)
    )
    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception as e:
        print(f"ERREUR détaillée lors de fetch_token: {traceback.format_exc()}")
        return jsonify({"error": f"Échec de la récupération des tokens OAuth: {e}."}), 500

    credentials = flow.credentials
    with open(TOKEN_PICKLE_FILE, 'wb') as token_file:
        pickle.dump(credentials, token_file)

    return """
    <html><head><title>Authentification Réussie</title></head>
    <body><h1>Authentification Google Réussie!</h1><p>Vous pouvez fermer cette fenêtre.</p>
    <script>setTimeout(function() { window.close(); }, 1000);</script></body></html>
    """

def list_next_10_calendar_events():
    creds = get_google_credentials()
    if not creds: return "Authentification Google requise. Veuillez autoriser via /authorize_google."
    try:
        service = build('calendar', 'v3', credentials=creds)
        now_utc = datetime.datetime.utcnow().isoformat() + 'Z'
        events_result = service.events().list(calendarId='primary', timeMin=now_utc,
                                              maxResults=10, singleEvents=True,
                                              orderBy='startTime').execute()
        events = events_result.get('items', [])
        if not events: return "Aucun événement à venir trouvé."
        # This detailed text is for panel_data
        response_text = "Voici vos 10 prochains événements :\n"
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            try:
                if 'T' in start: 
                    dt_object_utc = datetime.datetime.fromisoformat(start.replace('Z', '+00:00'))
                    dt_object_paris = dt_object_utc.astimezone(datetime.timezone(datetime.timedelta(hours=2))) 
                    start_formatted = dt_object_paris.strftime("%d %B %Y à %H:%M")
                else: 
                    dt_object_date = datetime.datetime.strptime(start, "%Y-%m-%d")
                    start_formatted = dt_object_date.strftime("%d %B %Y")
            except ValueError: 
                start_formatted = start 
            response_text += f"- {event['summary']} (le {start_formatted})\n"
        return response_text
    except HttpError as error:
        print(f"Erreur API Calendar: {error.resp.status} - {error._get_reason()}")
        if error.resp.status == 401 or 'invalid_grant' in str(error).lower():
            if os.path.exists(TOKEN_PICKLE_FILE): os.remove(TOKEN_PICKLE_FILE)
            return "Identifiants Calendar invalides/révoqués. Réauthentifiez-vous."
        return f"Erreur lors de l'accès à Calendar: {error.resp.status} - {error._get_reason()}"
    except Exception as e:
        print(f"Erreur inattendue lors de l'accès à Calendar: {e}")
        traceback.print_exc()
        return f"Erreur inattendue lors de l'accès à Calendar: {type(e).__name__}"

def list_unread_emails(max_results=10):
    creds = get_google_credentials()
    if not creds: return "Authentification Google requise pour Gmail. Veuillez autoriser via /authorize_google."
    try:
        service = build('gmail', 'v1', credentials=creds)
        results = service.users().messages().list(userId='me', labelIds=['INBOX', 'UNREAD'], maxResults=max_results).execute()
        messages = results.get('messages', [])
        if not messages: return "Aucun e-mail non lu trouvé."
        # This detailed text is for panel_data
        email_list_details = "Voici vos derniers e-mails non lus :\n"
        for msg_ref in messages:
            msg = service.users().messages().get(userId='me', id=msg_ref['id'], format='metadata', metadataHeaders=['Subject', 'From']).execute()
            headers = msg.get('payload', {}).get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'Pas de sujet')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Expéditeur inconnu')
            email_list_details += f"- De: {sender}, Sujet: {subject}\n"
        return email_list_details
    except HttpError as error:
        print(f"Erreur API Gmail (lecture): {error.resp.status} - {error._get_reason()}")
        if error.resp.status == 401 or 'invalid_grant' in str(error).lower():
            if os.path.exists(TOKEN_PICKLE_FILE): os.remove(TOKEN_PICKLE_FILE)
            return "Identifiants Gmail invalides/révoqués. Réauthentifiez-vous."
        return f"Erreur lors de l'accès à Gmail: {error.resp.status} - {error._get_reason()}"
    except Exception as e:
        print(f"Erreur inattendue lors de l'accès à Gmail (lecture): {e}")
        traceback.print_exc()
        return f"Erreur inattendue lors de l'accès à Gmail: {type(e).__name__}"

def send_email(to_address, subject, message_text):
    creds = get_google_credentials()
    if not creds: return "Authentification Google requise pour envoyer des e-mails. Veuillez autoriser via /authorize_google."
    try:
        service = build('gmail', 'v1', credentials=creds)
        mime_message = MIMEText(message_text, 'plain', 'utf-8') 
        mime_message['to'] = to_address
        mime_message['subject'] = subject
        encoded_message = base64.urlsafe_b64encode(mime_message.as_bytes()).decode()
        create_message_body = {'raw': encoded_message}
        service.users().messages().send(userId='me', body=create_message_body).execute()
        # This is a confirmation message.
        return f"E-mail envoyé avec succès à {to_address} avec l'objet '{subject}'."
    except HttpError as error:
        error_content = error.content.decode('utf-8') if error.content else "Aucun détail."
        print(f"Erreur API Gmail (envoi): {error.resp.status} - {error.resp.reason} - {error_content}")
        if error.resp.status == 401 or 'invalid_grant' in str(error).lower():
            if os.path.exists(TOKEN_PICKLE_FILE): os.remove(TOKEN_PICKLE_FILE)
            return "Identifiants Gmail invalides/révoqués. Réauthentifiez-vous."
        elif error.resp.status == 400: 
            return f"Erreur lors de la préparation de l'e-mail (400): {error_content}. Vérifiez l'adresse du destinataire."
        return f"Erreur lors de l'envoi de l'e-mail ({error.resp.status}): {error_content}"
    except Exception as e:
        print(f"Erreur inattendue lors de l'envoi de l'e-mail (Gmail): {e}")
        traceback.print_exc()
        return f"Erreur inattendue lors de l'envoi de l'e-mail: {type(e).__name__}"

def create_google_task(title, notes=None):
    creds = get_google_credentials()
    if not creds: return "Authentification Google requise pour créer des tâches. Veuillez autoriser via /authorize_google."
    if not title or not title.strip(): return "Le titre de la tâche ne peut pas être vide."
    try:
        service = build('tasks', 'v1', credentials=creds)
        tasklists_response = service.tasklists().list(maxResults=10).execute()
        tasklists = tasklists_response.get('items', [])
        tasklist_id = None
        tasklist_title = "par défaut" 

        if not tasklists: 
            try:
                created_list = service.tasklists().insert(body={'title': 'Ma Liste'}).execute()
                tasklist_id = created_list['id']
                tasklist_title = created_list['title']
            except HttpError as list_error:
                print(f"Erreur lors de la création de la liste de tâches par défaut: {list_error}")
                return "Aucune liste de tâches trouvée et la création automatique a échoué."
        else:
            preferred_list_titles = ["ma liste", "my tasks", "tâches", "tasks"] 
            for tl in tasklists:
                if tl.get('title', '').lower() in preferred_list_titles:
                    tasklist_id = tl['id']
                    tasklist_title = tl['title']
                    break
            if not tasklist_id: 
                tasklist_id = tasklists[0]['id']
                tasklist_title = tasklists[0].get('title', 'inconnue')

        task_body = {'title': title}
        if notes and notes.strip(): task_body['notes'] = notes
        created_task = service.tasks().insert(tasklist=tasklist_id, body=task_body).execute()
        # This is a confirmation message.
        return f"Tâche '{created_task['title']}' ajoutée à la liste '{tasklist_title}'."
    except HttpError as error:
        error_content = error.content.decode('utf-8') if error.content else "Aucun détail."
        print(f"Erreur API Tasks (création): {error.resp.status} - {error.resp.reason} - {error_content}")
        if error.resp.status == 401 or 'invalid_grant' in str(error).lower():
            if os.path.exists(TOKEN_PICKLE_FILE): os.remove(TOKEN_PICKLE_FILE)
            return "Identifiants Tasks invalides/révoqués. Réauthentifiez-vous."
        return f"Erreur lors de la création de la tâche ({error.resp.status}): {error_content}."
    except Exception as e:
        print(f"Erreur inattendue lors de la création de la tâche (Tasks): {e}")
        traceback.print_exc()
        return f"Erreur inattendue lors de la création de la tâche: {type(e).__name__}"

def list_google_tasks(max_results=10):
    creds = get_google_credentials()
    if not creds: return "Authentification Google requise pour Tasks. Veuillez autoriser via /authorize_google."
    try:
        service = build('tasks', 'v1', credentials=creds)
        all_tasklists_response = service.tasklists().list(maxResults=20).execute() 
        all_tasklists = all_tasklists_response.get('items', [])
        if not all_tasklists: return "Aucune liste de tâches trouvée."

        tasklist_id = all_tasklists[0]['id'] 
        tasklist_title = all_tasklists[0].get('title', 'par défaut')
        preferred_list_titles = ["ma liste", "my tasks", "tâches", "tasks"] 
        for tl in all_tasklists:
            if tl.get('title', '').lower() in preferred_list_titles:
                tasklist_id = tl['id']
                tasklist_title = tl['title']
                break
        
        results = service.tasks().list(tasklist=tasklist_id, maxResults=max_results, showCompleted=False, showHidden=False).execute()
        tasks = results.get('items', [])
        if not tasks: return f"Aucune tâche active trouvée dans la liste '{tasklist_title}'."
        # This detailed text is for panel_data
        task_list_details = f"Voici vos tâches actives de la liste '{tasklist_title}' :\n"
        for task in tasks:
            task_list_details += f"- {task.get('title', 'Tâche sans titre')}\n"
            if task.get('notes'):
                task_list_details += f"  Notes: {task.get('notes')}\n"
        return task_list_details
    except HttpError as error:
        error_content = error.content.decode('utf-8') if error.content else "Aucun détail."
        print(f"Erreur API Tasks (lecture): {error.resp.status} - {error.resp.reason} - {error_content}")
        if error.resp.status == 401 or 'invalid_grant' in str(error).lower():
            if os.path.exists(TOKEN_PICKLE_FILE): os.remove(TOKEN_PICKLE_FILE)
            return "Identifiants Tasks invalides/révoqués. Réauthentifiez-vous."
        return f"Erreur lors de l'accès à Tasks ({error.resp.status}): {error_content}"
    except Exception as e:
        print(f"Erreur inattendue lors de l'accès à Tasks (lecture): {e}")
        traceback.print_exc()
        return f"Erreur inattendue lors de l'accès à Tasks: {type(e).__name__}"

# --- Fonctions Google Maps et Recherche Web ---
def get_directions_from_google_maps_api(origin, destination):
    global google_maps_api_key
    if not google_maps_api_key:
         print("ERREUR: Clé API Google Maps non configurée.")
         return "Clé API Google Maps non configurée sur le serveur."
    try:
        import googlemaps 
        gmaps_client = googlemaps.Client(key=google_maps_api_key)
        directions_result = gmaps_client.directions(origin, destination, language="fr", mode="driving")

        if directions_result and len(directions_result) > 0:
            leg = directions_result[0]['legs'][0] 
            # This detailed text is for panel_data
            route_summary = f"Itinéraire de {origin} à {destination}:\n"
            route_summary += f"  Distance: {leg['distance']['text']}, Durée: {leg['duration']['text']}\n"
            if len(leg['steps']) > 0:
                route_summary += "  Étapes:\n"
                for i, step in enumerate(leg['steps'][:5]): 
                    clean_instructions = re.sub(r'<[^>]+>', '', step['html_instructions']) 
                    route_summary += f"    {i+1}. {clean_instructions} ({step['distance']['text']})\n"
                if len(leg['steps']) > 5:
                    route_summary += "    Et plus...\n"
            return route_summary
        else:
            return f"Impossible de trouver un itinéraire de {origin} à {destination}."
    except ImportError:
        print("ERREUR CRITIQUE: Bibliothèque 'googlemaps' non trouvée. Pour l'installer: pip install googlemaps")
        return "Erreur serveur: bibliothèque 'googlemaps' manquante."
    except Exception as e:
        print(f"Erreur lors du calcul de l'itinéraire: {e}")
        traceback.print_exc()
        return f"Erreur lors du calcul de l'itinéraire: {type(e).__name__}"

def perform_web_search(query, num_results=6): 
    global serpapi_client_available, serpapi_api_key
    if not serpapi_client_available:
        return "Service de recherche web non configuré ou bibliothèque manquante."
    try:
        params = { "q": query, "api_key": serpapi_api_key, "num": num_results, "hl": "fr", "gl": "fr" }
        search = GoogleSearch(params)
        results = search.get_dict()
        
        organic_results = results.get("organic_results", [])

        if not organic_results:
            answer_box = results.get("answer_box")
            if answer_box and (answer_box.get("answer") or answer_box.get("snippet")):
                # This detailed text is for panel_data
                return f"Réponse directe pour '{query}':\n{answer_box.get('answer') or answer_box.get('snippet')}"
            knowledge_graph = results.get("knowledge_graph")
            if knowledge_graph and knowledge_graph.get("description"):
                 # This detailed text is for panel_data
                 return f"Information pour '{query}':\n{knowledge_graph['description']}"
            return f"Aucun résultat pertinent pour '{query}'."

        # This detailed text is for panel_data
        summary_details = f"Résultats web pour '{query}':\n"
        for i, res in enumerate(organic_results[:num_results]): 
            summary_details += f"{i+1}. {res.get('title', 'Sans titre')}\n"
            summary_details += f"   Extrait: {res.get('snippet', 'N/A')}\n" 
            summary_details += f"   Source: {res.get('link', '#')}\n\n" 

        if results.get("answer_box") and (results["answer_box"].get("answer") or results["answer_box"].get("snippet")):
            summary_details += f"Info complémentaire:\n{results['answer_box'].get('answer') or results['answer_box'].get('snippet')}\n\n"

        return summary_details.strip()
    except Exception as e:
        print(f"Erreur lors de la recherche web SerpAPI: {e}")
        traceback.print_exc()
        return f"Erreur lors de la recherche web : {type(e).__name__}"

# --- Fonctions Gemini et gTTS ---
def get_gemini_response(current_user_parts):
    global generative_model, gemini_conversation_history, MAX_HISTORY_ITEMS
    if not generative_model: return "Client Gemini non configuré."

    api_request_contents = list(gemini_conversation_history) 
    if current_user_parts:
        api_request_contents.append({"role": "user", "parts": current_user_parts})
    elif not api_request_contents: 
        return "Rien à envoyer à Gemini."

    try:
        response = generative_model.generate_content(api_request_contents)
        response_text = ""
        if hasattr(response, 'text'): 
            response_text = response.text
        elif hasattr(response, 'parts') and response.parts: 
             response_text = "".join([p.text for p in response.parts if hasattr(p, 'text')])
        else: 
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
                return f"Réponse Gemini bloquée ({response.prompt_feedback.block_reason_message or response.prompt_feedback.block_reason})."
            
            candidate = response.candidates[0] if hasattr(response, 'candidates') and response.candidates else None
            if candidate and hasattr(candidate, 'content') and hasattr(candidate.content, 'parts') and candidate.content.parts:
                 response_text = "".join([p.text for p in candidate.content.parts if hasattr(p, 'text')])
            elif candidate and hasattr(candidate, 'finish_reason') and candidate.finish_reason != 'STOP':
                 return f"Réponse Gemini incomplète/bloquée ({candidate.finish_reason})."
            else: 
                 try:
                     response_text = response.text 
                 except:
                     print("WARN: Impossible d'extraire 'text' ou 'parts' de la réponse Gemini. La réponse pourrait être un JSON de commande.")
                     if hasattr(response, 'candidates') and response.candidates and \
                        hasattr(response.candidates[0], 'content') and hasattr(response.candidates[0].content, 'parts'):
                         potential_json_str = "".join(p.text for p in response.candidates[0].content.parts if hasattr(p, 'text'))
                         if potential_json_str.strip().startswith("{") and potential_json_str.strip().endswith("}"):
                             response_text = potential_json_str 
                         else:
                             return "Gemini n'a pas généré de réponse textuelle claire ni de JSON de commande valide."
                     else: 
                         return "Réponse de Gemini non interprétable comme texte ou JSON de commande."

        if current_user_parts: 
            gemini_conversation_history.append({"role": "user", "parts": current_user_parts})
        
        is_command_json = False
        if isinstance(response_text, str) and response_text.strip().startswith("{") and response_text.strip().endswith("}"):
            try:
                parsed_json = json.loads(response_text)
                if isinstance(parsed_json, dict) and "action" in parsed_json:
                    is_command_json = True
            except json.JSONDecodeError:
                pass 

        if not is_command_json and response_text and not any(err in str(response_text) for err in ["bloquée", "simulée", "incomplète"]): 
            gemini_conversation_history.append({"role": "model", "parts": [{"text": str(response_text)}]}) 
        
        if len(gemini_conversation_history) > MAX_HISTORY_ITEMS * 2: 
            gemini_conversation_history = gemini_conversation_history[-(MAX_HISTORY_ITEMS * 2):]
        
        return response_text
    except Exception as e:
        print(f"Erreur API Gemini: {e}")
        traceback.print_exc()
        return f"Erreur API Gemini: {type(e).__name__}" + (f" - {e.args[0]}" if e.args else "")


def get_gtts_audio(text_to_speak, lang='fr'):
    global gtts_enabled
    if not gtts_enabled or not text_to_speak: return None
    cleaned_text = re.sub(r'[\*\/\:\\\"#]', '', text_to_speak) 
    if not cleaned_text.strip(): return None 

    try:
        tts = gTTS(text=cleaned_text, lang=lang, slow=False)
        audio_fp = io.BytesIO()
        tts.write_to_fp(audio_fp)
        audio_fp.seek(0)
        return f"data:audio/mpeg;base64,{base64.b64encode(audio_fp.read()).decode('utf-8')}"
    except Exception as e:
        print(f"Erreur gTTS: {e}")
        return None

# --- NLU Action Handlers ---
# These handlers now return the DETAILED string, which will be used for panel_data.
# The chat_ws function will craft the short chat_display_message.
def handle_create_calendar_event(entities):
    summary = entities.get("summary")
    datetime_str = entities.get("datetime_str")
    if summary and datetime_str:
        start_dt_obj = parse_french_datetime(datetime_str)
        if start_dt_obj:
            return create_calendar_event(summary, start_dt_obj)
        else:
            return f"Je n'ai pas pu interpréter la date et l'heure '{datetime_str}'. Pouvez-vous reformuler plus clairement (ex: '15 juin à 14h30') ?"
    return "Pour créer un événement, j'ai besoin d'un titre et d'une date/heure (ex: 'Réunion projet demain à 10h')."

def handle_list_calendar_events(entities):
    return list_next_10_calendar_events()

def handle_send_email(entities):
    recipient_name_or_email = entities.get("recipient_name_or_email")
    subject = entities.get("subject", "Sans objet") 
    body = entities.get("body")

    if not recipient_name_or_email:
        return "À qui dois-je envoyer cet e-mail ?"
    if not body:
        return "Quel est le message que vous souhaitez envoyer ?"

    to_address = None
    if re.match(r"[^@]+@[^@]+\.[^@]+", recipient_name_or_email):
        to_address = recipient_name_or_email
    else: 
        to_address = get_contact_email(recipient_name_or_email)
        if not to_address:
            return f"Je n'ai pas trouvé le contact '{recipient_name_or_email}' dans votre carnet d'adresses."
    
    return send_email(to_address, subject, body)

def handle_list_emails(entities):
    return list_unread_emails()

def handle_create_task(entities):
    title = entities.get("title")
    notes = entities.get("notes") 
    if title:
        return create_google_task(title, notes)
    return "Quel est le titre de la tâche que vous souhaitez ajouter ?"

def handle_list_tasks(entities):
    return list_google_tasks()

def handle_add_contact(entities):
    name = entities.get("name")
    email = entities.get("email")
    if name and email:
        return add_contact_to_book(name, email)
    return "Pour ajouter un contact, veuillez me donner son nom et son adresse e-mail."

def handle_list_contacts(entities):
    return list_contacts_from_book()

def handle_remove_contact(entities):
    name = entities.get("name")
    if name:
        return remove_contact_from_book(name)
    return "Quel contact souhaitez-vous supprimer ?"

def handle_get_contact_email(entities):
    name = entities.get("name")
    if name:
        email_addr = get_contact_email(name)
        return f"L'adresse e-mail de {name} est {email_addr}." if email_addr else f"Contact '{name}' non trouvé."
    return "De quel contact souhaitez-vous connaître l'adresse e-mail ?"

def handle_get_directions(entities):
    origin = entities.get("origin", "Thonon-les-Bains") 
    destination = entities.get("destination")
    if destination:
        return get_directions_from_google_maps_api(origin, destination)
    return "Veuillez préciser la destination pour l'itinéraire."

def handle_web_search(entities):
    query = entities.get("query")
    if query:
        return perform_web_search(query)
    return "Que souhaitez-vous rechercher sur le web ?"

def handle_google_keep_info(entities): 
    return "Désolé, Google Keep n'a pas d'API publique officielle, je ne peux donc pas gérer vos notes Keep directement."

def handle_get_weather_forecast(entities):
    # The client fetches weather, backend just acknowledges and provides a trigger phrase for the panel.
    return "Prévisions météo pour votre localisation." # This will be panel_data

action_dispatcher = {
    "create_calendar_event": handle_create_calendar_event,
    "list_calendar_events": handle_list_calendar_events,
    "send_email": handle_send_email,
    "list_emails": handle_list_emails,
    "create_task": handle_create_task,
    "list_tasks": handle_list_tasks,
    "add_contact": handle_add_contact,
    "list_contacts": handle_list_contacts,
    "remove_contact": handle_remove_contact,
    "get_contact_email": handle_get_contact_email,
    "get_directions": handle_get_directions,
    "web_search": handle_web_search,
    "google_keep_info": handle_google_keep_info,
    "get_weather_forecast": handle_get_weather_forecast, 
}

# --- WebSocket Handler ---
@sock.route('/api/chat_ws')
def chat_ws(ws):
    global gemini_conversation_history
    last_activity_time = time.time()
    server_ping_interval = 30 
    client_receive_timeout = 5 

    try:
        while True:
            current_time = time.time()
            raw_data = None
            try:
                raw_data = ws.receive(timeout=client_receive_timeout)
            except (ConnectionClosed, ConnectionResetError):
                raise 
            except Exception: 
                pass 

            if raw_data is not None:
                last_activity_time = current_time 
                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError:
                    print(f"ERREUR: Données WebSocket non JSON reçues: {raw_data}")
                    ws.send(json.dumps({"type": "error", "message": "Invalid JSON."}))
                    continue

                user_text = data.get('text', '')
                image_data_url = data.get('imageData')

                current_user_parts_for_gemini = []
                if user_text: current_user_parts_for_gemini.append(user_text)
                if image_data_url:
                    try:
                        header, encoded = image_data_url.split(",", 1)
                        image_bytes = base64.b64decode(encoded)
                        img = Image.open(io.BytesIO(image_bytes))
                        current_user_parts_for_gemini.append(img)
                    except Exception as e:
                        print(f"Erreur lors du décodage de l'image: {e}")
                
                final_text_response = None # This will hold the DETAILED response from actions
                action_taken_by_nlu = False 
                parsed_command_action = None # To store the action string if NLU identifies one

                if not current_user_parts_for_gemini and not gemini_conversation_history:
                    final_text_response = "Veuillez fournir une requête ou une image."
                else:
                    gemini_raw_response = get_gemini_response(current_user_parts_for_gemini)
                    response_to_parse = gemini_raw_response
                    if isinstance(gemini_raw_response, str):
                        temp_response = gemini_raw_response.strip()
                        if temp_response.startswith("```json"):
                            temp_response = temp_response[len("```json"):].strip()
                        elif temp_response.startswith("```"): 
                             temp_response = temp_response[len("```"):].strip()
                        if temp_response.endswith("```"):
                            temp_response = temp_response[:-len("```")].strip()
                        response_to_parse = temp_response
                    
                    try:
                        parsed_command = json.loads(response_to_parse)
                        if isinstance(parsed_command, dict) and "action" in parsed_command:
                            parsed_command_action = parsed_command.get("action")
                            entities = parsed_command.get("entities", {})
                            
                            if parsed_command_action in action_dispatcher:
                                final_text_response = action_dispatcher[parsed_command_action](entities)
                                action_taken_by_nlu = True
                            else:
                                print(f"WARN [chat_ws] Action NLU JSON non reconnue: {parsed_command_action}")
                                final_text_response = gemini_raw_response 
                        else:
                            final_text_response = gemini_raw_response 
                    except json.JSONDecodeError:
                        final_text_response = gemini_raw_response 
                    except Exception as e_nlu:
                        print(f"ERREUR [chat_ws] lors du traitement de la réponse NLU de Gemini: {e_nlu}")
                        traceback.print_exc()
                        final_text_response = "Une erreur s'est produite lors de l'interprétation de votre demande."

                if final_text_response is None: 
                    final_text_response = "Je ne suis pas sûr de comprendre votre demande."

                # --- Prepare message for client (chat vs panel) ---
                chat_display_message = str(final_text_response) # Default: chat shows full/error response
                panel_data_content = None
                panel_target_id = None
                
                # These actions are simple confirmations, panel_data is not needed or handled by client.
                simple_confirmation_actions = ["create_calendar_event", "send_email", "create_task", "add_contact", "remove_contact", "get_contact_email", "google_keep_info"]

                if action_taken_by_nlu and parsed_command_action not in simple_confirmation_actions:
                    panel_data_content = str(final_text_response) # The detailed content for the panel

                    if parsed_command_action == "list_calendar_events":
                        panel_target_id = "calendarContent"
                        chat_display_message = "Voici les événements du calendrier." if "Aucun événement" not in panel_data_content else panel_data_content
                    elif parsed_command_action == "list_emails":
                        panel_target_id = "emailContent"
                        chat_display_message = "Voici vos e-mails." if "Aucun e-mail non lu" not in panel_data_content else panel_data_content
                    elif parsed_command_action == "list_tasks":
                        panel_target_id = "taskContent"
                        chat_display_message = "Voici la liste des tâches." if "Aucune tâche active" not in panel_data_content else panel_data_content
                    elif parsed_command_action == "list_contacts":
                        panel_target_id = "searchContent" # Display in search panel for now, or create new
                        chat_display_message = "Voici la liste de vos contacts." if "carnet d'adresses est vide" not in panel_data_content else panel_data_content
                    elif parsed_command_action == "get_directions":
                        panel_target_id = "mapContent" # For textual directions summary
                        chat_display_message = "Voici votre itinéraire." if "Impossible de trouver" not in panel_data_content else panel_data_content
                    elif parsed_command_action == "web_search":
                        panel_target_id = "searchContent"
                        query_entity = parsed_command.get("entities", {}).get("query", "")
                        chat_display_message = f"Voici les résultats de recherche pour '{query_entity}'." if "Aucun résultat pertinent" not in panel_data_content and "non configuré" not in panel_data_content else panel_data_content
                    elif parsed_command_action == "get_weather_forecast":
                        panel_target_id = "weatherForecastContent"
                        chat_display_message = "Voici les prévisions météo."
                        # panel_data_content is "Prévisions météo pour votre localisation." - client uses this as a trigger.
                
                # Construct the message to send to the client
                message_to_send = {"type": "final_text", "text": chat_display_message}
                if panel_data_content and panel_target_id:
                    message_to_send["panel_data"] = panel_data_content
                    message_to_send["panel_target_id"] = panel_target_id
                
                ws.send(json.dumps(message_to_send))
                
                # --- Audio Generation Logic (uses chat_display_message) ---
                audio_data_url = None
                text_for_gtts = chat_display_message 
                should_speak = True 
                lower_chat_message = chat_display_message.lower()
                is_code_response_in_chat = "```" in chat_display_message 

                if is_code_response_in_chat and not panel_data_content : # If chat message is code and not a panel action
                    text_for_gtts = "Voici le code que j'ai généré."
                elif action_taken_by_nlu:
                    if parsed_command_action in simple_confirmation_actions:
                        text_for_gtts = chat_display_message # Speak the confirmation like "Email envoyé"
                    elif any(kw in chat_display_message for kw in ["Voici les", "Voici vos", "Voici la liste"]):
                         text_for_gtts = chat_display_message # Speak the short intro
                    elif any(err_kw in lower_chat_message for err_kw in ["erreur", "non trouvé", "invalide", "pas pu interpréter", "j'ai besoin", "veuillez préciser", "dois-je", "souhaitez-vous"]):
                        text_for_gtts = chat_display_message # Speak errors/clarifications
                    else: # Fallback for other NLU actions that might have short chat messages
                        text_for_gtts = chat_display_message
                
                suppress_audio_keywords = [
                    "authentification google requise", "identifiants invalides/révoqués",
                    "erreur api gemini", "client gemini non configuré", "réponse gemini bloquée",
                    "erreur critique", "erreur serveur", "erreur interne",
                    "bibliothèque manquante", "non disponible",
                    "je ne suis pas sûr de comprendre votre demande" 
                ]
                if not is_code_response_in_chat:
                    if any(keyword in lower_chat_message for keyword in suppress_audio_keywords):
                        if text_for_gtts == chat_display_message: 
                             should_speak = False
                
                if chat_display_message.strip() == "" or lower_chat_message == "ok.": 
                    should_speak = False

                if should_speak:
                    audio_data_url = get_gtts_audio(text_for_gtts, lang='fr')

                if audio_data_url:
                    ws.send(json.dumps({"type": "audio_data", "audio": audio_data_url}))
                else:
                    ws.send(json.dumps({"type": "no_audio_data"}))

            else: 
                if current_time - last_activity_time > server_ping_interval:
                    try:
                        ws.send(json.dumps({"type": "system_ping", "timestamp": current_time}))
                        last_activity_time = current_time 
                    except (ConnectionClosed, ConnectionResetError):
                        raise 
                    except Exception as e_ping:
                        print(f"ERREUR lors de l'envoi du ping serveur: {type(e_ping).__name__} - {e_ping}")
                        traceback.print_exc()
                        raise 

    except (ConnectionClosed, ConnectionResetError):
        pass 
    except Exception as e:
        print(f"[ERREUR WebSocket Handler Critique] /api/chat_ws: {type(e).__name__} - {e}")
        traceback.print_exc()
        try:
            if hasattr(ws, 'connected') and ws.connected: 
                 ws.send(json.dumps({"type": "error", "message": f"Erreur serveur: {type(e).__name__}"}))
        except Exception as send_error:
            print(f"Impossible d'envoyer le message d'erreur final au client: {send_error}")
    finally:
        pass 


if __name__ == '__main__':
    if not os.path.exists(CLIENT_SECRETS_FILE):
        print(f"AVERTISSEMENT: Fichier '{CLIENT_SECRETS_FILE}' manquant. OAuth Google sera désactivé.")
    if not google_maps_api_key:
        print(f"AVERTISSEMENT: Variable d'environnement GOOGLE_MAPS_API_KEY manquante. Les itinéraires Google Maps seront désactivés.")

    print("-------------------------------------------")
    print(f"Démarrage du serveur Flask sur http://localhost:5000")
    print(f"Endpoint WebSocket: ws://localhost:5000/api/chat_ws")
    print(f"Mode debug Flask: {'Activé' if app.debug else 'Désactivé'}") 
    print(f"Modèle Gemini: {gemini_model_name}")
    print(f"gTTS: {'Oui' if gtts_enabled else 'Non'}")
    print(f"SerpAPI: {'Oui' if serpapi_client_available and serpapi_api_key else 'Non'}")
    print(f"Google Maps API: {'Oui' if google_maps_api_key else 'Non'}")
    print(f"Lien d'autorisation Google OAuth: http://localhost:5000/authorize_google")
    print(f"Fichier de tokens OAuth: {TOKEN_PICKLE_FILE}")
    print(f"Fichier de contacts: {CONTACTS_FILE}")
    print("-------------------------------------------")
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
