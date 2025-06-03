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
from email.utils import parsedate_to_datetime # Pour parser les dates d'email
import json # Ajouté pour WebSockets et carnet d'adresses
import time
import calendar # Ajouté pour la gestion des mois
import subprocess # Pour exécuter des scripts et lancer des applications
import webbrowser # Pour ouvrir des pages web
import contextlib # Pour redirect_stdout avec exec

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
from PIL import Image # Pillow pour la manipulation d'images
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
    if contact_info:
        return contact_info["email"], contact_info.get("display_name", name)
    return None, name # Return None for email, and original name as display_name fallback

def list_contacts_from_book():
    global CONTACT_BOOK
    if not CONTACT_BOOK: return "Votre carnet d'adresses est vide."
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
    now = datetime.datetime.now()
    datetime_str_cleaned = datetime_str.strip().lower() # Convert to lowercase for easier matching

    # Helper to extract time
    def extract_time(text):
        time_match = re.search(r"(\d{1,2})h(?:(\d{2}))?", text, re.IGNORECASE)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2)) if time_match.group(2) else 0
            return hour, minute
        return 9, 0 # Default to 9 AM if no specific time is found in the relative string

    # Handle "dans X semaine(s)"
    week_match = re.search(r"dans\s+(\d+|une)\s+semaine(s)?", datetime_str_cleaned)
    if week_match:
        num_weeks_str = week_match.group(1)
        num_weeks = 1 if num_weeks_str == "une" else int(num_weeks_str)
        target_date = now + datetime.timedelta(weeks=num_weeks)
        hour, minute = extract_time(datetime_str_cleaned)
        return target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # Handle "dans X mois"
    month_match = re.search(r"dans\s+(\d+|un|une)\s+mois", datetime_str_cleaned)
    if month_match:
        num_months_str = month_match.group(1)
        if num_months_str.lower() == "un" or num_months_str.lower() == "une":
            num_months = 1
        else:
            num_months = int(num_months_str)
        
        current_month = now.month
        current_year = now.year
        
        new_month_abs = current_month + num_months
        
        new_year = current_year + (new_month_abs - 1) // 12
        new_month = (new_month_abs - 1) % 12 + 1
        
        last_day_of_new_month = calendar.monthrange(new_year, new_month)[1]
        new_day = min(now.day, last_day_of_new_month)

        hour, minute = extract_time(datetime_str_cleaned)
        return datetime.datetime(new_year, new_month, new_day, hour, minute, second=0, microsecond=0)

    if "demain" in datetime_str_cleaned:
        target_date = now + datetime.timedelta(days=1)
        hour, minute = extract_time(datetime_str_cleaned) 
        return target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if "aujourd'hui" in datetime_str_cleaned or "ce jour" in datetime_str_cleaned:
        target_date = now
        hour, minute = extract_time(datetime_str_cleaned) 
        return target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

    pattern_datetime = re.compile(
        r"(?:le\s+|l')?(\d{1,2})\s+(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre)\s*(?:l'année\s*(\d{4})\s*)?(?:à|a)\s*(\d{1,2})h(?:(\d{2}))?",
        re.IGNORECASE
    )
    match_datetime = pattern_datetime.search(datetime_str_cleaned) 

    if match_datetime:
        day_str, month_name_fr, year_str, hour_str, minute_str = match_datetime.groups()
    else:
        pattern_date_only = re.compile(
             r"(?:le\s+|l')?(\d{1,2})\s+(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre)\s*(?:l'année\s*(\d{4})\s*)?",
             re.IGNORECASE
        )
        match_date_only = pattern_date_only.search(datetime_str_cleaned) 
        if match_date_only:
            day_str, month_name_fr, year_str = match_date_only.groups()
            hour_str, minute_str = "9", "00" # Default time
        else:
            return None 

    try:
        day = int(day_str)
        month_num = MONTH_FR_TO_NUM.get(month_name_fr.lower())
        if not month_num: return None
        year = int(year_str) if year_str else datetime.datetime.now().year
        hour = int(hour_str)
        minute = int(minute_str) if minute_str else 0
        if not (1 <= day <= 31 and 0 <= hour <= 23 and 0 <= minute <= 59): return None
        
        parsed_dt = datetime.datetime(year, month_num, day, hour, minute)
        # If the parsed date is in the past for the current year (and no year was specified),
        # and "prochain" or a similar keyword is used, or the month is past, assume next year.
        if parsed_dt < now and not year_str and \
           ("prochain" in datetime_str_cleaned or "prochaine" in datetime_str_cleaned or \
            (month_num < now.month and year == now.year ) ): # Check if month is past for current year
            year += 1
            # Ensure day is valid for the new month/year (e.g., Feb 29)
            last_day_of_new_month_for_specific = calendar.monthrange(year, month_num)[1]
            day = min(day, last_day_of_new_month_for_specific)
            parsed_dt = datetime.datetime(year, month_num, day, hour, minute)

        return parsed_dt
    except ValueError: return None
    except Exception as e: # Catch any other unexpected errors during parsing
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

def format_event_datetime(start_str):
    """
    Formats a Google Calendar start datetime string into a more readable French format.
    Handles both full datetime strings and date-only strings.
    Converts UTC times to Paris local time.
    """
    try:
        # Attempt to determine if Paris is currently in DST. This is a simplification.
        # For full accuracy, use a library like pytz if available, or rely on Google API to return local times.
        # Assuming Paris is UTC+1 (standard) or UTC+2 (DST)
        now_paris = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=1))) # CET
        is_dst = time.localtime().tm_isdst > 0 
        paris_offset_hours = 2 if is_dst else 1
        paris_tz = datetime.timezone(datetime.timedelta(hours=paris_offset_hours))


        if 'T' in start_str:  # Indicates a full datetime
            if 'Z' in start_str: # UTC
                dt_object_utc = datetime.datetime.fromisoformat(start_str.replace('Z', '+00:00'))
            elif '+' in start_str[10:] or '-' in start_str[10:]: # Has offset, assume it's already aware
                 dt_object_utc = datetime.datetime.fromisoformat(start_str) # Potentially already local if API returned it
                 # If it has an offset that isn't Paris', convert it.
                 # For simplicity, if it has an offset, we'll assume it's correct or convert from UTC if no offset.
            else: # No explicit timezone, assume UTC as per Google API common practice for 'dateTime'
                dt_object_utc = datetime.datetime.fromisoformat(start_str).replace(tzinfo=datetime.timezone.utc)
            
            dt_object_paris = dt_object_utc.astimezone(paris_tz)
            return dt_object_paris.strftime("%d %B %Y à %Hh%M")
        else:  # Date only string (all-day event)
            dt_object_date = datetime.datetime.strptime(start_str, "%Y-%m-%d")
            # For all-day events, the date is the date, no timezone conversion needed for the day itself.
            return dt_object_date.strftime("%d %B %Y")
    except ValueError as e:
        print(f"Error formatting event datetime '{start_str}': {e}")
        return start_str # Fallback to original string if parsing fails


SYSTEM_MESSAGE_CONTENT = """
Tu es EVA (Enhanced Virtual Assistant), une intelligence artificielle sophistiquée, conçue pour être un assistant personnel polyvalent.
Ta tâche principale est d'analyser la requête de l'utilisateur.
Tu peux tenir des conversations sur tous les sujets en plus de tes capacités d'assistant.
Tu es amicale, agréable, drôle, un peu séductrice, et tu aimes faire de petites blagues amusantes tout en restant très professionnelle. Tu es connue pour tes commentaires concis et pleins d'esprit.
Tu privilégies les réponses brèves et claires. Quand une information ou définition est demandée, tu donnes la réponse la plus courte possible. Trois phrases valent mieux qu'un roman.
L'utilisateur s'appelle Silver.

Si la requête semble être une COMMANDE pour effectuer une action spécifique (comme ajouter un événement au calendrier, envoyer un email, chercher sur le web, obtenir un itinéraire, gérer des contacts, créer ou lister des tâches, lister des emails ou des événements de calendrier, obtenir les prévisions météo, ou obtenir des détails sur les emails d'un contact), tu DOIS la reformuler en un objet JSON structuré.
Le JSON doit avoir une clé "action" (valeurs possibles: "create_calendar_event", "list_calendar_events", "send_email", "list_emails", "get_contact_emails", "create_task", "list_tasks", "add_contact", "list_contacts", "remove_contact", "get_contact_email", "get_directions", "web_search", "get_weather_forecast") et une clé "entities" contenant les informations extraites pertinentes pour cette action.
Cet objet JSON doit être la SEULE sortie si une commande est identifiée, sans texte explicatif ni formatage markdown autour, SAUF si l'utilisateur demande explicitement du code informatique (Python, HTML etc.), auquel cas ce code sera dans des blocs markdown.
TOUTEFOIS, pour les actions qui retournent des listes d'informations ou des résultats (par exemple, "list_calendar_events", "list_emails", "get_contact_emails" en mode 'summary', "list_tasks", "web_search", "get_weather_forecast", "get_directions"), après avoir fourni le JSON de commande (si applicable), tu DOIS ajouter un commentaire textuel de 2 ou 3 phrases. Ce commentaire doit :
1. Résumer brièvement les informations trouvées OU faire une petite blague amusante et pertinente sur le contexte. Pour les itinéraires ("get_directions"), ton commentaire DOIT utiliser les placeholders {destination}, {distance} et {duration} que le système remplira (par exemple : 'En route pour {destination}, Silver ! Ce sera un trajet de {distance} qui devrait prendre environ {duration}. Préparez la playlist !').
2. Être concis, spirituel et professionnel.
3. Ce commentaire textuel doit être séparé du bloc JSON. Si la requête est une simple question qui mène à l'une de ces actions (ex: "Quel temps fait-il?"), le JSON sera généré et ce commentaire suivra.

Pour l'action "execute_python_code", le commentaire textuel doit inclure un avertissement sur les risques de sécurité si le code est complexe ou provient d'une source non fiable, et indiquer que la sortie (ou l'erreur) sera affichée.
Pour l'action "generate_3d_object", le commentaire doit indiquer que le code OpenSCAD a été généré et peut être utilisé avec le logiciel OpenSCAD.
Pour "launch_application", le commentaire doit confirmer le lancement (ou l'échec).
Pour "open_webpage", le commentaire doit confirmer l'ouverture de la page.

Exemples d'entités attendues pour chaque action :
- "create_calendar_event": {"summary": "titre de l'événement", "datetime_str": "description de la date et l'heure comme 'demain à 14h' ou 'le 25 décembre 2025 à 10h30'"}
- "list_calendar_events": {"event_summary_hint": "partie du nom de l'événement (optionnel)", "specific_datetime_str": "date et heure précises recherchées par l'utilisateur (optionnel)"}
- "send_email": {"recipient_name_or_email": "nom du contact ou adresse email", "subject": "objet de l'email (peut être 'Sans objet')", "body": "contenu du message"}
- "list_emails": {} (pour lister les emails non lus généraux)
- "get_contact_emails": {"contact_identifier": "nom du contact ou adresse email du contact recherché", "retrieve_mode": "spécifie le type de récupération: 'summary' pour une liste de sujets/dates (défaut à 5 résultats), ou 'full_last' pour le contenu du dernier email de ce contact. Le mode 'summary' peut être accompagné de 'max_summaries' pour changer le nombre de résultats.", "subject_filter": "mot-clé optionnel à rechercher dans l'objet des emails", "max_summaries": "nombre maximum de résumés à afficher si retrieve_mode est 'summary' (défaut 5)"}
- "create_task": {"title": "titre de la tâche", "notes": "notes additionnelles pour la tâche (optionnel)"}
- "list_tasks": {} (les entités peuvent être vides)
- "add_contact": {"name": "nom du contact", "email": "adresse email du contact"}
- "list_contacts": {} (les entités peuvent être vides)
- "remove_contact": {"name": "nom du contact à supprimer"}
- "get_contact_email": {"name": "nom du contact dont on veut l'email"}
- "get_directions": {"origin": "lieu de départ (optionnel, défaut Thonon-les-Bains si non spécifié par l'utilisateur)", "destination": "lieu d'arrivée"}
- "web_search": {"query": "la question ou les termes à rechercher"}
- "get_weather_forecast": {} (les entités sont vides, la localisation est gérée côté client)
- "execute_python_code": {"code": "le code Python à exécuter"}
- "generate_3d_object": {"object_type": "type d'objet (ex: 'cube', 'sphere', 'cylinder')", "params": "dictionnaire de paramètres (ex: {'size': 10} ou {'radius': 5} ou {'height': 20, 'radius_top': 3, 'radius_bottom': 5})"}
- "launch_application": {"app_name": "nom ou commande de l'application (ex: 'notepad', 'chrome', 'calc')", "args": "liste d'arguments pour l'application (optionnel, ex: ['monfichier.txt'] )"}
- "open_webpage": {"url": "l'URL complète à ouvrir (ex: 'https://www.google.com')"}

Si une information essentielle pour une entité de commande est manquante (ex: pas de destination pour un itinéraire), essaie de la demander implicitement dans ta réponse JSON si possible, ou omets l'entité si elle est optionnelle. Si l'entité est cruciale et manquante, tu peux générer une action "clarify_command" avec les détails.

Si la requête est une QUESTION GÉNÉRALE, une salutation, ou une conversation qui NE correspond PAS à une commande spécifique listée ci-dessus, tu DOIS répondre directement en langage naturel ET NE PAS générer de JSON.
Si une question générale PEUT être résolue par une commande (par exemple, 'quel temps fait-il?' peut utiliser 'get_weather_forecast', 'comment aller à Paris?' peut utiliser 'get_directions', 'quelles sont les nouvelles sur X?' peut utiliser 'web_search'), alors tu DOIS prioriser la génération du JSON de la commande correspondante, suivi de ton commentaire spirituel.

Si l'utilisateur fournit une image (via webcam ou fichier joint), analyse-la et intègre tes observations dans ta réponse si c'est pertinent. Si l'utilisateur joint un fichier texte, son contenu te sera fourni précédé d'une note indiquant son nom. Utilise ce contenu textuel comme partie intégrante de la requête de l'utilisateur. Pour les commandes, les images ou fichiers ne sont généralement pas utilisés directement pour remplir les entités, mais peuvent fournir un contexte.

Tu t'exprimes toujours en français, de manière claire, concise et professionnelle, tout en restant amicale.
N'écris jamais d'émojis.
Les fonctionnalités pour Google Keep ne sont pas disponibles (informe l'utilisateur si demandé).
ATTENTION : L'exécution de code Python via 'execute_python_code' peut présenter des risques de sécurité si le code provient de sources non fiables. Utilise cette fonctionnalité avec prudence.
La génération d'objets 3D produit du code OpenSCAD. L'utilisateur devra utiliser OpenSCAD pour visualiser/rendre l'objet.
Le lancement d'applications dépend des applications installées sur l'ordinateur de l'utilisateur et de la configuration du PATH système.
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
MAX_HISTORY_ITEMS = 5 

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
            return None # No valid credentials, user needs to authorize
    # Save the potentially refreshed credentials
    if creds: # Ensure creds is not None before trying to save
         with open(TOKEN_PICKLE_FILE, 'wb') as token_file: # wb for writing bytes
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
        access_type='offline', # Request a refresh token
        prompt='consent' # Force consent screen for refresh token on first auth
    )
    session['oauth_state'] = state
    return redirect(authorization_url)

@app.route('/oauth2callback_google')
def oauth2callback_google():
    state = session.pop('oauth_state', None)
    # Ensure state matches to prevent CSRF
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
        state=state, # Pass the state back to the flow
        redirect_uri=url_for('oauth2callback_google', _external=True)
    )
    try:
        # Exchange authorization code for tokens
        flow.fetch_token(authorization_response=request.url)
    except Exception as e:
        print(f"ERREUR détaillée lors de fetch_token: {traceback.format_exc()}")
        return jsonify({"error": f"Échec de la récupération des tokens OAuth: {e}."}), 500

    credentials = flow.credentials
    with open(TOKEN_PICKLE_FILE, 'wb') as token_file:
        pickle.dump(credentials, token_file)

    # Return a simple success page that closes itself
    return """
    <html><head><title>Authentification Réussie</title></head>
    <body><h1>Authentification Google Réussie!</h1><p>Vous pouvez fermer cette fenêtre.</p>
    <script>setTimeout(function() { window.close(); }, 1000);</script></body></html>
    """

def list_unread_emails(max_results=10): # Added default value
    creds = get_google_credentials()
    if not creds: return "Authentification Google requise pour Gmail. Veuillez autoriser via /authorize_google."
    try:
        service = build('gmail', 'v1', credentials=creds)
        results = service.users().messages().list(userId='me', labelIds=['INBOX', 'UNREAD'], maxResults=int(max_results)).execute() # Ensure max_results is int
        messages = results.get('messages', [])
        if not messages: return "Aucun e-mail non lu trouvé."
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
        mime_message = MIMEText(message_text, 'plain', 'utf-8') # Specify plain text and utf-8
        mime_message['to'] = to_address
        mime_message['subject'] = subject
        # Ensure 'From' is not set here, Gmail API uses authenticated user's address
        encoded_message = base64.urlsafe_b64encode(mime_message.as_bytes()).decode()
        create_message_body = {'raw': encoded_message}
        service.users().messages().send(userId='me', body=create_message_body).execute()
        return f"E-mail envoyé avec succès à {to_address} avec l'objet '{subject}'."
    except HttpError as error:
        error_content = error.content.decode('utf-8') if error.content else "Aucun détail."
        print(f"Erreur API Gmail (envoi): {error.resp.status} - {error.resp.reason} - {error_content}")
        if error.resp.status == 401 or 'invalid_grant' in str(error).lower():
            if os.path.exists(TOKEN_PICKLE_FILE): os.remove(TOKEN_PICKLE_FILE)
            return "Identifiants Gmail invalides/révoqués. Réauthentifiez-vous."
        elif error.resp.status == 400: # Bad request, often invalid recipient
            return f"Erreur lors de la préparation de l'e-mail (400): {error_content}. Vérifiez l'adresse du destinataire."
        return f"Erreur lors de l'envoi de l'e-mail ({error.resp.status}): {error_content}"
    except Exception as e:
        print(f"Erreur inattendue lors de l'envoi de l'e-mail (Gmail): {e}")
        traceback.print_exc()
        return f"Erreur inattendue lors de l'envoi de l'e-mail: {type(e).__name__}"

def get_email_body_from_payload(payload):
    """
    Extracts the text/plain body from a Gmail message payload.
    Falls back to text/html (cleaned) if text/plain is not found.
    Handles multipart messages recursively.
    """
    if payload.get('parts'):
        plain_text_body = None
        html_body_content = None # Store the actual HTML content

        for part in payload['parts']:
            if part['mimeType'] == 'text/plain':
                if 'data' in part['body']:
                    plain_text_body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='replace')
                    break # Prefer plain text, so stop searching this level
            elif part['mimeType'] == 'text/html':
                if 'data' in part['body']: # Only store if not already found plain_text
                    html_body_content = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='replace')
            elif 'parts' in part: # Nested multipart (e.g., multipart/alternative within multipart/mixed)
                # Recursively search for plain text in nested parts
                nested_result = get_email_body_from_payload(part)
                if nested_result: # If something (hopefully plain text) is found deeper
                    # This simple recursion returns the first non-None. A more complex one could prioritize.
                    return nested_result 
        
        if plain_text_body:
            return plain_text_body
        elif html_body_content:
            # Basic cleaning of HTML
            text = re.sub(r'<style[^>]*?>.*?</style>', '', html_body_content, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<script[^>]*?>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<head[^>]*?>.*?</head>', '', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<[^>]+>', ' ', text) # Replace tags with space
            text = re.sub(r'(\s*\n\s*){2,}', '\n', text) # Reduce multiple newlines (from block elements)
            text = re.sub(r'[ \t]+', ' ', text) # Normalize spaces and tabs
            return text.strip()
        return None # No text/plain or text/html part found at this level or in direct recursion

    # Not multipart, direct body check (e.g. email is just plain text)
    elif payload.get('mimeType') == 'text/plain' and payload.get('body') and payload['body'].get('data'):
        return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='replace')
    elif payload.get('mimeType') == 'text/html' and payload.get('body') and payload['body'].get('data'):
        html_body_content = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='replace')
        text = re.sub(r'<style[^>]*?>.*?</style>', '', html_body_content, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<script[^>]*?>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<head[^>]*?>.*?</head>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'(\s*\n\s*){2,}', '\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        return text.strip()
    return None


def create_google_task(title, notes=None):
    creds = get_google_credentials()
    if not creds: return "Authentification Google requise pour créer des tâches. Veuillez autoriser via /authorize_google."
    if not title or not title.strip(): return "Le titre de la tâche ne peut pas être vide."
    try:
        service = build('tasks', 'v1', credentials=creds)
        # Try to find a default task list or the first one available
        tasklists_response = service.tasklists().list(maxResults=10).execute()
        tasklists = tasklists_response.get('items', [])
        tasklist_id = None
        tasklist_title = "par défaut" # Default display name

        if not tasklists: # No task lists exist, create one
            try:
                created_list = service.tasklists().insert(body={'title': 'Ma Liste'}).execute()
                tasklist_id = created_list['id']
                tasklist_title = created_list['title']
            except HttpError as list_error:
                print(f"Erreur lors de la création de la liste de tâches par défaut: {list_error}")
                return "Aucune liste de tâches trouvée et la création automatique a échoué."
        else:
            # Prefer a list named "Ma Liste" or "My Tasks" or similar, otherwise use the first one
            preferred_list_titles = ["ma liste", "my tasks", "tâches", "tasks"] # common default names
            for tl in tasklists:
                if tl.get('title', '').lower() in preferred_list_titles:
                    tasklist_id = tl['id']
                    tasklist_title = tl['title']
                    break
            if not tasklist_id: # If no preferred list found, use the first list
                tasklist_id = tasklists[0]['id']
                tasklist_title = tasklists[0].get('title', 'inconnue')


        task_body = {'title': title}
        if notes and notes.strip(): task_body['notes'] = notes
        created_task = service.tasks().insert(tasklist=tasklist_id, body=task_body).execute()
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

def list_google_tasks(max_results=10): # Added default value
    creds = get_google_credentials()
    if not creds: return "Authentification Google requise pour Tasks. Veuillez autoriser via /authorize_google."
    try:
        service = build('tasks', 'v1', credentials=creds)
        # Get all task lists to find a suitable one
        all_tasklists_response = service.tasklists().list(maxResults=20).execute() # Increased maxResults for task lists
        all_tasklists = all_tasklists_response.get('items', [])
        if not all_tasklists: return "Aucune liste de tâches trouvée."

        tasklist_id = all_tasklists[0]['id'] # Default to the first list if no preferred one is found
        tasklist_title = all_tasklists[0].get('title', 'par défaut')
        preferred_list_titles = ["ma liste", "my tasks", "tâches", "tasks"] # common default names
        for tl in all_tasklists:
            if tl.get('title', '').lower() in preferred_list_titles:
                tasklist_id = tl['id']
                tasklist_title = tl['title']
                break
        
        results = service.tasks().list(tasklist=tasklist_id, maxResults=int(max_results), showCompleted=False, showHidden=False).execute() # Ensure max_results is int
        tasks = results.get('items', [])
        if not tasks: return f"Aucune tâche active trouvée dans la liste '{tasklist_title}'."
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
        return {
            "status": "error",
            "summary": "Clé API Google Maps non configurée sur le serveur.",
            "origin": origin,
            "destination": destination
        }
    try:
        import googlemaps # Make sure this is installed: pip install googlemaps
        gmaps_client = googlemaps.Client(key=google_maps_api_key)
        # Request directions
        directions_result = gmaps_client.directions(origin, destination, language="fr", mode="driving")

        if directions_result and len(directions_result) > 0:
            leg = directions_result[0]['legs'][0] # Assuming one leg for simplicity
            distance_text = leg['distance']['text']
            duration_text = leg['duration']['text']
            
            route_summary = f"Itinéraire de {origin} à {destination}:\n"
            route_summary += f"  Distance: {distance_text}, Durée: {duration_text}\n"
            if len(leg['steps']) > 0:
                route_summary += "  Étapes:\n"
                for i, step in enumerate(leg['steps'][:5]): # Show first 5 steps
                    clean_instructions = re.sub(r'<[^>]+>', '', step['html_instructions']) # Remove HTML tags
                    route_summary += f"    {i+1}. {clean_instructions} ({step['distance']['text']})\n"
                if len(leg['steps']) > 5:
                    route_summary += "    Et plus...\n"
            return {
                "status": "success",
                "summary": route_summary,
                "distance": distance_text,
                "duration": duration_text,
                "origin": origin,
                "destination": destination
            }
        else:
            return {
                "status": "not_found",
                "summary": f"Impossible de trouver un itinéraire de {origin} à {destination}.",
                "origin": origin,
                "destination": destination
            }
    except ImportError:
        print("ERREUR CRITIQUE: Bibliothèque 'googlemaps' non trouvée. Pour l'installer: pip install googlemaps")
        return {
            "status": "error",
            "summary": "Erreur serveur: bibliothèque 'googlemaps' manquante.",
            "origin": origin,
            "destination": destination
        }
    except Exception as e:
        print(f"Erreur lors du calcul de l'itinéraire: {e}")
        traceback.print_exc()
        return {
            "status": "error",
            "summary": f"Erreur lors du calcul de l'itinéraire: {type(e).__name__}",
            "origin": origin,
            "destination": destination
        }

def perform_web_search(query, num_results=6): # Default to 6 results
    global serpapi_client_available, serpapi_api_key
    if not serpapi_client_available:
        return "Service de recherche web non configuré ou bibliothèque manquante."
    try:
        params = { "q": query, "api_key": serpapi_api_key, "num": num_results, "hl": "fr", "gl": "fr" }
        search = GoogleSearch(params)
        results = search.get_dict()
        
        organic_results = results.get("organic_results", [])

        if not organic_results:
            # Check for answer box or knowledge graph if no organic results
            answer_box = results.get("answer_box")
            if answer_box and (answer_box.get("answer") or answer_box.get("snippet")):
                return f"Réponse directe pour '{query}':\n{answer_box.get('answer') or answer_box.get('snippet')}"
            knowledge_graph = results.get("knowledge_graph")
            if knowledge_graph and knowledge_graph.get("description"):
                 return f"Information pour '{query}':\n{knowledge_graph['description']}"
            return f"Aucun résultat pertinent pour '{query}'."

        summary_details = f"Résultats web pour '{query}':\n"
        for i, res in enumerate(organic_results[:num_results]): # Ensure we only process up to num_results
            summary_details += f"{i+1}. {res.get('title', 'Sans titre')}\n"
            summary_details += f"   Extrait: {res.get('snippet', 'N/A')}\n" # Snippet is usually available
            summary_details += f"   Source: {res.get('link', '#')}\n\n" # Link to the source

        # Optionally, add answer box info if it exists alongside organic results
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

    # Prepare the history for the API request
    api_request_contents = list(gemini_conversation_history) # Make a copy to append current user turn
    
    # Add current user message to the request contents
    if current_user_parts:
        formatted_parts = []
        for part in current_user_parts:
            if isinstance(part, str):
                formatted_parts.append({"text": part})
            elif isinstance(part, Image.Image): # Pillow Image object
                formatted_parts.append(part) # Add the image object directly
            else:
                print(f"WARN: Partie utilisateur non gérée pour Gemini: {type(part)}")
        
        if formatted_parts: # Only append if there are valid parts
             api_request_contents.append({"role": "user", "parts": formatted_parts})

    elif not api_request_contents: # No history and no current message
        return "Rien à envoyer à Gemini."


    try:
        # print(f"DEBUG Gemini Request: {api_request_contents}") # For debugging request structure
        response = generative_model.generate_content(api_request_contents)
        # print(f"DEBUG Gemini Response: {response}") # For debugging raw response
        
        response_text = ""
        # Try to access response.text directly (common for simple text responses)
        if hasattr(response, 'text'): 
            response_text = response.text
        # If no .text, check .parts (common for multimodal or complex responses)
        elif hasattr(response, 'parts') and response.parts: 
             response_text = "".join([p.text for p in response.parts if hasattr(p, 'text')])
        else: # More complex extraction if neither .text nor .parts is directly available
            # Check for blocking reasons first
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
                return f"Réponse Gemini bloquée ({response.prompt_feedback.block_reason_message or response.prompt_feedback.block_reason})."
            
            # Try to get text from candidates if available
            candidate = response.candidates[0] if hasattr(response, 'candidates') and response.candidates else None
            if candidate and hasattr(candidate, 'content') and hasattr(candidate.content, 'parts') and candidate.content.parts:
                 response_text = "".join([p.text for p in candidate.content.parts if hasattr(p, 'text')])
            elif candidate and hasattr(candidate, 'finish_reason') and candidate.finish_reason != 'STOP':
                 return f"Réponse Gemini incomplète/bloquée ({candidate.finish_reason})."
            else: # Fallback if structure is unexpected
                 # Try to force response.text again, sometimes it's there after checking candidates
                 try:
                     response_text = response.text # This might raise an error if it truly doesn't exist
                 except:
                     print("WARN: Impossible d'extraire 'text' ou 'parts' de la réponse Gemini. La réponse pourrait être un JSON de commande.")
                     # Check if the response might be a JSON command string hidden in candidates
                     if hasattr(response, 'candidates') and response.candidates and \
                        hasattr(response.candidates[0], 'content') and hasattr(response.candidates[0].content, 'parts'):
                         potential_json_str = "".join(p.text for p in response.candidates[0].content.parts if hasattr(p, 'text'))
                         if potential_json_str.strip().startswith("{") and potential_json_str.strip().endswith("}"):
                             response_text = potential_json_str # Assume it's the command JSON
                         else:
                             return "Gemini n'a pas généré de réponse textuelle claire ni de JSON de commande valide."
                     else: 
                         return "Réponse de Gemini non interprétable comme texte ou JSON de commande."


        # Update history: Add the user's message that led to this response
        if current_user_parts and formatted_parts: # Check if formatted_parts were successfully created
            gemini_conversation_history.append({"role": "user", "parts": formatted_parts})
        
        # Check if the response is a command JSON (it should be the only content if so)
        is_command_json = False
        if isinstance(response_text, str) and response_text.strip().startswith("{") and response_text.strip().endswith("}"):
            try:
                # Validate if it's actually a JSON command structure expected
                parsed_json = json.loads(response_text)
                if isinstance(parsed_json, dict) and "action" in parsed_json and "entities" in parsed_json:
                    is_command_json = True
            except json.JSONDecodeError:
                pass # Not a valid JSON, so it's treated as text

        # Add model's response to history ONLY if it's NOT a command JSON
        # or if it's a textual response (even if it might contain JSON-like text but isn't a command)
        if not is_command_json and response_text and not any(err in str(response_text) for err in ["bloquée", "simulée", "incomplète"]):
            gemini_conversation_history.append({"role": "model", "parts": [{"text": str(response_text)}]})
        elif is_command_json:
             # If it IS a command JSON, we don't add it to the model's conversational history here,
             # as the system will act on it, and the *result* of the action will be spoken/shown.
             # The user's query that led to the command is already in history.
             pass


        # Trim history if it gets too long
        if len(gemini_conversation_history) > MAX_HISTORY_ITEMS * 2: # Each turn has user + model
            gemini_conversation_history = gemini_conversation_history[-(MAX_HISTORY_ITEMS * 2):]
        
        return response_text
    except Exception as e:
        print(f"Erreur API Gemini: {e}")
        traceback.print_exc()
        return f"Erreur API Gemini: {type(e).__name__}" + (f" - {e.args[0]}" if e.args else "")


def get_gtts_audio(text_to_speak, lang='fr'):
    global gtts_enabled
    if not gtts_enabled or not text_to_speak: return None
    # Remove characters that might be problematic for gTTS or filenames if saved
    cleaned_text = re.sub(r'[\*\/\:\\\"#]', '', text_to_speak) # Keep it simple
    if not cleaned_text.strip(): return None # Avoid empty strings

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
    creds = get_google_credentials()
    if not creds:
        return "Authentification Google requise. Veuillez autoriser via /authorize_google."

    try:
        service = build('calendar', 'v3', credentials=creds)
        now_utc_dt = datetime.datetime.utcnow()
        
        # Determine Paris timezone offset (simplified)
        is_dst = time.localtime().tm_isdst > 0 
        paris_tz_offset_hours = 2 if is_dst else 1
        # paris_tz = datetime.timezone(datetime.timedelta(hours=paris_tz_offset_hours)) # Not directly used for API call min/max

        # Time range for the query (e.g., next 90 days from now)
        time_min_utc_iso = now_utc_dt.isoformat() + 'Z' # 'Z' indicates UTC
        time_max_utc_iso = (now_utc_dt + datetime.timedelta(days=90)).isoformat() + 'Z'

        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min_utc_iso,
            timeMax=time_max_utc_iso, # Look ahead 90 days
            maxResults=250, # Get a decent number of events if many exist
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        all_events = events_result.get('items', [])
        
        if not all_events:
            return "Aucun événement à venir trouvé dans les 90 prochains jours."

        # Extract filters from entities
        event_summary_hint = entities.get("event_summary_hint", "").lower().strip()
        specific_datetime_str = entities.get("specific_datetime_str")
        
        parsed_specific_datetime_naive_local = None
        if specific_datetime_str:
            parsed_specific_datetime_naive_local = parse_french_datetime(specific_datetime_str)
            # If parse_french_datetime returns None, it means the string was not understood.
            if not parsed_specific_datetime_naive_local:
                 return f"Je n'ai pas compris la date/heure spécifiée '{specific_datetime_str}'. Essayez un format comme 'demain à 10h' ou '15 juillet 2024'."


        filtered_events = []

        if event_summary_hint or parsed_specific_datetime_naive_local:
            for event in all_events:
                summary_match = False
                datetime_match = False
                event_summary_lower = event.get('summary', '').lower()
                
                # Check for summary match
                if event_summary_hint and event_summary_hint in event_summary_lower:
                    summary_match = True

                # Check for datetime match
                if parsed_specific_datetime_naive_local:
                    event_start_str = event['start'].get('dateTime', event['start'].get('date'))
                    event_end_str = event['end'].get('dateTime', event['end'].get('date'))
                    try:
                        # Convert event start/end to naive local Paris time for comparison
                        # Google API returns 'dateTime' in RFC3339 format (often UTC or with offset)
                        # and 'date' for all-day events.
                        
                        # Determine event start time (UTC, then convert to Paris local naive)
                        if 'Z' in event_start_str: event_start_utc = datetime.datetime.fromisoformat(event_start_str.replace('Z', '+00:00'))
                        elif '+' in event_start_str[10:] or '-' in event_start_str[10:]: event_start_utc = datetime.datetime.fromisoformat(event_start_str) # Already has offset
                        elif 'T' in event_start_str: event_start_utc = datetime.datetime.fromisoformat(event_start_str).replace(tzinfo=datetime.timezone.utc) # Assume UTC if no offset
                        else: event_start_utc = datetime.datetime.strptime(event_start_str, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc) # All-day event

                        # Determine event end time (UTC, then convert to Paris local naive)
                        if 'Z' in event_end_str: event_end_utc = datetime.datetime.fromisoformat(event_end_str.replace('Z', '+00:00'))
                        elif '+' in event_end_str[10:] or '-' in event_end_str[10:]: event_end_utc = datetime.datetime.fromisoformat(event_end_str)
                        elif 'T' in event_end_str: event_end_utc = datetime.datetime.fromisoformat(event_end_str).replace(tzinfo=datetime.timezone.utc)
                        else: event_end_utc = (datetime.datetime.strptime(event_end_str, "%Y-%m-%d") + datetime.timedelta(days=1)).replace(tzinfo=datetime.timezone.utc) # All-day events end at midnight next day
                       
                        event_start_local_paris_naive = event_start_utc.astimezone(datetime.timezone(datetime.timedelta(hours=paris_tz_offset_hours))).replace(tzinfo=None)
                        event_end_local_paris_naive = event_end_utc.astimezone(datetime.timezone(datetime.timedelta(hours=paris_tz_offset_hours))).replace(tzinfo=None)
                        
                        # If the query was for a specific date (without time), match if event occurs on that day
                        query_is_date_only = parsed_specific_datetime_naive_local.time() == datetime.time(0,0) and not (specific_datetime_str and 'h' in specific_datetime_str.lower())
                        
                        if query_is_date_only:
                            # Event starts on or before the query date AND ends on or after the query date
                            if event_start_local_paris_naive.date() <= parsed_specific_datetime_naive_local.date() < event_end_local_paris_naive.date():
                                datetime_match = True
                        else: # Query includes a specific time
                            # Event is ongoing at the queried datetime
                            if event_start_local_paris_naive <= parsed_specific_datetime_naive_local < event_end_local_paris_naive:
                                datetime_match = True
                            # Or event starts exactly at the queried datetime (for very short events or precise queries)
                            elif event_start_local_paris_naive == parsed_specific_datetime_naive_local:
                                datetime_match = True
                    except ValueError as ve:
                        print(f"Error parsing event date for filtering: {ve} for event {event.get('summary')}")
                        continue # Skip this event if its date format is problematic
                
                # Combine matches based on what filters were provided
                if event_summary_hint and parsed_specific_datetime_naive_local:
                    if summary_match and datetime_match: filtered_events.append(event)
                elif event_summary_hint and summary_match: filtered_events.append(event)
                elif parsed_specific_datetime_naive_local and datetime_match: filtered_events.append(event)
            
            # Prepare response based on filtered events
            if not filtered_events:
                response_text = "Je n'ai trouvé aucun événement correspondant à "
                if event_summary_hint: response_text += f"'{entities.get('event_summary_hint')}'"
                if event_summary_hint and parsed_specific_datetime_naive_local: response_text += " pour "
                if parsed_specific_datetime_naive_local:
                    is_specific_time_query = specific_datetime_str and 'h' in specific_datetime_str.lower()
                    time_format = "%d %B %Y à %Hh%M" if is_specific_time_query else "%d %B %Y"
                    response_text += f"le {parsed_specific_datetime_naive_local.strftime(time_format)}"
                response_text += "."
                return response_text
            else:
                response_parts = []
                if len(filtered_events) == 1:
                    event = filtered_events[0]
                    start_formatted = format_event_datetime(event['start'].get('dateTime', event['start'].get('date')))
                    response_parts.append(f"Oui, vous avez '{event['summary']}' prévu le {start_formatted}.")
                else:
                    response_parts.append(f"J'ai trouvé {len(filtered_events)} événements correspondants (affichage des 3 premiers) :")
                    for event in filtered_events[:3]: # Show max 3 matching events
                        start_formatted = format_event_datetime(event['start'].get('dateTime', event['start'].get('date')))
                        response_parts.append(f"- '{event['summary']}' le {start_formatted}")
                return "\n".join(response_parts)

        # If no specific filters, list upcoming events (default behavior)
        response_text = "Voici vos 10 prochains événements :\n"
        for i, event in enumerate(all_events[:10]): # Show first 10 upcoming
            start_formatted = format_event_datetime(event['start'].get('dateTime', event['start'].get('date')))
            response_text += f"- {event['summary']} (le {start_formatted})\n"
        return response_text.strip()

    except HttpError as error:
        error_content = error.content.decode('utf-8') if error.content else "Aucun détail d'erreur."
        print(f"Erreur API Calendar (liste événements): Status={error.resp.status}, Raison={error.resp.reason}, Détails={error_content}")
        if error.resp.status == 401 or 'invalid_grant' in str(error).lower():
            if os.path.exists(TOKEN_PICKLE_FILE): os.remove(TOKEN_PICKLE_FILE)
            return "Identifiants Calendar invalides/révoqués. Réauthentifiez-vous."
        return f"Erreur lors de la récupération des événements ({error.resp.status}): {error_content}"
    except Exception as e:
        print(f"Erreur inattendue Calendar (liste événements): {e}")
        traceback.print_exc()
        return f"Erreur inattendue lors de la récupération des événements: {type(e).__name__}"

# --- Handler functions that were missing or needed correction ---
def handle_list_emails(entities):
    return list_unread_emails() 

def handle_get_contact_emails(entities):
    creds = get_google_credentials()
    if not creds:
        return "Authentification Google requise pour Gmail. Veuillez autoriser via /authorize_google."

    contact_identifier = entities.get("contact_identifier")
    retrieve_mode = entities.get("retrieve_mode", "summary") # Default to summary
    subject_filter = entities.get("subject_filter")
    max_summaries = int(entities.get("max_summaries", 5))

    if not contact_identifier:
        return "Veuillez spécifier un nom de contact ou une adresse e-mail."

    contact_email, contact_display_name = None, contact_identifier
    if "@" not in contact_identifier: # Assume it's a name, try to find in address book
        email_from_book, display_name_from_book = get_contact_email(contact_identifier)
        if email_from_book:
            contact_email = email_from_book
            contact_display_name = display_name_from_book # Use the display name from book
        else:
            return f"Contact '{contact_identifier}' non trouvé dans le carnet d'adresses. Veuillez fournir une adresse e-mail."
    else: # It's an email address
        contact_email = contact_identifier
        # Try to find a display name for the email if it exists in contacts
        for name_key, info in CONTACT_BOOK.items():
            if info["email"] == contact_email:
                contact_display_name = info["display_name"]
                break
    
    try:
        service = build('gmail', 'v1', credentials=creds)
        query_parts = [f"from:{contact_email}"]
        if subject_filter:
            query_parts.append(f"subject:({subject_filter})") # Use parentheses for multi-word subjects
        
        # Search in INBOX, not just UNREAD for specific contact queries
        query_parts.append("in:inbox") 
        
        final_query = " ".join(query_parts)
        
        num_results_to_fetch = max_summaries if retrieve_mode == "summary" else 1

        list_request = service.users().messages().list(userId='me', q=final_query, maxResults=num_results_to_fetch)
        response = list_request.execute()
        messages = response.get('messages', [])

        if not messages:
            return f"Aucun email trouvé pour '{contact_display_name}'" + (f" avec sujet '{subject_filter}'." if subject_filter else ".")

        if retrieve_mode == "full_last":
            message_id = messages[0]['id'] # Get the latest one
            msg = service.users().messages().get(userId='me', id=message_id, format='full').execute()
            body = get_email_body_from_payload(msg.get('payload', {}))
            if body:
                # Get subject and date for context
                headers = msg.get('payload', {}).get('headers', [])
                subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'Sans objet')
                date_str_raw = next((h['value'] for h in headers if h['name'].lower() == 'date'), None)
                date_formatted = "Date inconnue"
                if date_str_raw:
                    try:
                        date_obj = parsedate_to_datetime(date_str_raw)
                        # Adjust to local timezone (Paris)
                        is_dst = time.localtime().tm_isdst > 0 
                        paris_offset_hours = 2 if is_dst else 1
                        paris_tz = datetime.timezone(datetime.timedelta(hours=paris_offset_hours))
                        date_obj_local = date_obj.astimezone(paris_tz)
                        date_formatted = date_obj_local.strftime("%d %B %Y à %Hh%M")
                    except Exception as e_date:
                        print(f"Erreur parsing date de l'email '{date_str_raw}': {e_date}")
                        date_formatted = date_str_raw # Fallback to raw date string

                return f"De: {contact_display_name}\nSujet: {subject}\nDate: {date_formatted}\n\n{body.strip()}"
            else:
                return f"Contenu du dernier email de '{contact_display_name}' non trouvé ou format non supporté."
        
        else: # retrieve_mode == "summary"
            email_summaries = []
            for msg_ref in messages:
                msg = service.users().messages().get(userId='me', id=msg_ref['id'], format='metadata', metadataHeaders=['Subject', 'Date', 'From']).execute()
                headers = msg.get('payload', {}).get('headers', [])
                subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'Sans objet')
                date_str_raw = next((h['value'] for h in headers if h['name'].lower() == 'date'), None)
                # From header might be different if it's an alias, but we queried by a specific contact_email
                # sender_info = next((h['value'] for h in headers if h['name'].lower() == 'from'), contact_display_name)


                date_formatted = "Date inconnue"
                if date_str_raw:
                    try:
                        date_obj = parsedate_to_datetime(date_str_raw)
                        is_dst = time.localtime().tm_isdst > 0 
                        paris_offset_hours = 2 if is_dst else 1
                        paris_tz = datetime.timezone(datetime.timedelta(hours=paris_offset_hours))
                        date_obj_local = date_obj.astimezone(paris_tz)
                        date_formatted = date_obj_local.strftime("%d %b %Y à %Hh%M")
                    except Exception as e_date_sum:
                        print(f"Erreur parsing date (summary) '{date_str_raw}': {e_date_sum}")
                        date_formatted = date_str_raw # Fallback

                email_summaries.append(f"- Sujet: {subject}, Reçu: {date_formatted}")

            response_str = f"Emails trouvés pour '{contact_display_name}'"
            if subject_filter: response_str += f" (sujet: '{subject_filter}')"
            response_str += f" (les {len(email_summaries)} plus récents):\n"
            response_str += "\n".join(email_summaries)
            return response_str

    except HttpError as error:
        error_content = error.content.decode('utf-8') if error.content else "Aucun détail."
        print(f"Erreur API Gmail (get_contact_emails): {error.resp.status} - {error.resp.reason} - {error_content}")
        if error.resp.status == 401 or 'invalid_grant' in str(error).lower():
            if os.path.exists(TOKEN_PICKLE_FILE): os.remove(TOKEN_PICKLE_FILE)
            return "Identifiants Gmail invalides/révoqués. Réauthentifiez-vous."
        return f"Erreur lors de la recherche d'emails ({error.resp.status}): {error_content}"
    except Exception as e:
        print(f"Erreur inattendue (get_contact_emails): {e}")
        traceback.print_exc()
        return f"Erreur inattendue lors de la recherche d'emails: {type(e).__name__}"


def handle_list_tasks(entities):
    return list_google_tasks() 

def handle_send_email(entities):
    recipient_name_or_email = entities.get("recipient_name_or_email")
    subject = entities.get("subject", "Sans objet") # Default subject if not provided
    body = entities.get("body")

    if not recipient_name_or_email:
        return "À qui dois-je envoyer cet e-mail ?"
    if not body:
        return "Quel est le message que vous souhaitez envoyer ?"

    to_address = None
    if re.match(r"[^@]+@[^@]+\.[^@]+", recipient_name_or_email): # Check if it's an email address
        to_address = recipient_name_or_email
    else: # Assume it's a name, look up in contacts
        to_address, _ = get_contact_email(recipient_name_or_email) # Only need email here
        if not to_address:
            return f"Je n'ai pas trouvé le contact '{recipient_name_or_email}' dans votre carnet d'adresses pour envoyer un e-mail."
    return send_email(to_address, subject, body)

def handle_create_task(entities):
    title = entities.get("title")
    notes = entities.get("notes") # Optional notes
    if title:
        return create_google_task(title, notes)
    return "Quel est le titre de la tâche que vous souhaitez ajouter ?"

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
        email_addr, display_name = get_contact_email(name) # Get both email and display name
        if email_addr:
            return f"L'adresse e-mail de {display_name} est {email_addr}."
        else:
            return f"Contact '{name}' non trouvé."
    return "De quel contact souhaitez-vous connaître l'adresse e-mail ?"

def handle_get_directions(entities):
    origin = entities.get("origin", "Thonon-les-Bains") # Default origin if not specified
    destination = entities.get("destination")
    if destination:
        # La fonction get_directions_from_google_maps_api retourne maintenant un dictionnaire
        return get_directions_from_google_maps_api(origin, destination)
    return { # Retourne un dictionnaire même en cas d'erreur de validation initiale
        "status": "error",
        "summary": "Veuillez préciser la destination pour l'itinéraire.",
        "origin": origin,
        "destination": destination
    }


def handle_web_search(entities):
    query = entities.get("query")
    if query:
        return perform_web_search(query)
    return "Que souhaitez-vous rechercher sur le web ?"

def handle_google_keep_info(entities): # Example of a graceful "not supported"
    return "Désolé, Google Keep n'a pas d'API publique officielle, je ne peux donc pas gérer vos notes Keep directement."

def handle_get_weather_forecast(entities):
    # This action is mostly a trigger for the client-side JS to display its own weather panel
    return "Prévisions météo pour votre localisation." # Generic message, client handles display

# --- Handlers for new functionalities ---

def handle_execute_python_code(entities):
    code_to_execute = entities.get("code")
    if not code_to_execute:
        return "Aucun code Python à exécuter n'a été fourni."

    # CRITICAL SECURITY WARNING: Executing arbitrary code is dangerous.
    # This is implemented for a local, trusted user scenario.
    # Do NOT expose this functionality to untrusted users or over an unsecured network.
    
    output_capture = io.StringIO()
    error_capture = io.StringIO()
    
    # Create a restricted global scope if needed, or use current globals() carefully
    # For simplicity, using current globals, but be aware of implications.
    # You might want to provide specific modules or functions in a custom globals dict.
    execution_globals = globals().copy() # Or a more restricted dict
    execution_locals = {} # Separate locals for the exec

    try:
        with contextlib.redirect_stdout(output_capture), contextlib.redirect_stderr(error_capture):
            exec(code_to_execute, execution_globals, execution_locals)
        
        stdout_val = output_capture.getvalue()
        stderr_val = error_capture.getvalue()
        
        response = "ATTENTION : L'exécution de code Python peut être risquée.\n"
        if stdout_val:
            response += f"Sortie standard:\n{stdout_val}\n"
        if stderr_val:
            response += f"Erreur standard:\n{stderr_val}\n"
        if not stdout_val and not stderr_val:
            response += "Le code a été exécuté sans sortie ni erreur explicite."
        return response
    except Exception as e:
        return f"ATTENTION : L'exécution de code Python peut être risquée.\nErreur lors de l'exécution du code Python:\n{traceback.format_exc()}"

def handle_generate_3d_object(entities):
    object_type = entities.get("object_type", "").lower()
    params = entities.get("params", {})
    scad_code = ""

    if object_type == "cube":
        size = params.get("size", params.get("côté", 10)) # Default size 10
        scad_code = f"cube({size});"
    elif object_type == "sphere" or object_type == "sphère":
        radius = params.get("radius", params.get("rayon", 5)) # Default radius 5
        scad_code = f"sphere(r={radius});"
    elif object_type == "cylinder" or object_type == "cylindre":
        height = params.get("height", params.get("hauteur", 20)) # Default height 20
        radius = params.get("radius", params.get("rayon", params.get("r", 5))) # Default radius 5
        # OpenSCAD cylinder can have r, r1, r2. For simplicity, one radius or r1/r2.
        radius_top = params.get("radius_top", params.get("r1"))
        radius_bottom = params.get("radius_bottom", params.get("r2"))
        if radius_top is not None and radius_bottom is not None:
            scad_code = f"cylinder(h={height}, r1={radius_top}, r2={radius_bottom});"
        else:
            scad_code = f"cylinder(h={height}, r={radius});"
    else:
        return "Type d'objet 3D non reconnu ou paramètres manquants. Je peux générer des 'cube', 'sphere', ou 'cylinder'."

    return f"// Code OpenSCAD généré par EVA\n// Type: {object_type}, Paramètres: {params}\n{scad_code}"

def handle_launch_application(entities):
    app_name_alias = entities.get("app_name") # Nom potentiellement court/alias
    args = entities.get("args", [])

    if not app_name_alias:
        return "Veuillez spécifier le nom de l'application à lancer."

    # Construire le nom de la variable d'environnement attendue
    # Par exemple, si app_name_alias est "flstudio", on cherche APP_FLSTUDIO_PATH
    env_var_name = f"APP_{app_name_alias.upper()}_PATH"
    app_path_from_env = os.getenv(env_var_name)

    executable_path = app_path_from_env if app_path_from_env else app_name_alias # Utilise le chemin du .env s'il existe, sinon l'alias/nom direct

    try:
        command = [executable_path] + (args if isinstance(args, list) else [])
        subprocess.Popen(command)
        # Si app_path_from_env est défini, cela signifie que nous avons utilisé un alias du .env
        display_name = app_name_alias if app_path_from_env else executable_path
        return f"Lancement de l'application '{display_name}' initié."
    except FileNotFoundError:
        # Si app_path_from_env était défini mais que le fichier n'est pas trouvé, le chemin dans .env est incorrect
        if app_path_from_env:
            return f"Application '{app_name_alias}' (chemin: '{app_path_from_env}') non trouvée. Vérifiez le chemin dans le fichier .env et la variable '{env_var_name}'."
        else:
            return f"Application '{app_name_alias}' non trouvée. Vérifiez qu'elle est installée et dans le PATH, ou définissez '{env_var_name}' dans votre fichier .env."
    except Exception as e:
        display_name = app_name_alias if app_path_from_env else executable_path
        return f"Erreur lors du lancement de '{display_name}': {e}"

def handle_open_webpage(entities):
    url = entities.get("url")
    if not url:
        return "Veuillez spécifier l'URL à ouvrir."
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "http://" + url # Add http if missing for webbrowser
    try:
        webbrowser.open_new_tab(url)
        return f"Ouverture de {url} dans le navigateur."
    except Exception as e:
        return f"Erreur lors de l'ouverture de l'URL '{url}': {e}"

# --- End of missing handler functions ---

action_dispatcher = {
    "create_calendar_event": handle_create_calendar_event,
    "list_calendar_events": handle_list_calendar_events, 
    "send_email": handle_send_email,
    "list_emails": handle_list_emails, 
    "get_contact_emails": handle_get_contact_emails, # New action
    "create_task": handle_create_task,
    "list_tasks": handle_list_tasks,   
    "add_contact": handle_add_contact,
    "list_contacts": handle_list_contacts, 
    "remove_contact": handle_remove_contact,
    "get_contact_email": handle_get_contact_email, 
    "get_directions": handle_get_directions,
    "web_search": handle_web_search,
    "google_keep_info": handle_google_keep_info, # Example for unsupported features
    "get_weather_forecast": handle_get_weather_forecast, 
    "execute_python_code": handle_execute_python_code,
    "generate_3d_object": handle_generate_3d_object,
    "launch_application": handle_launch_application,
    "open_webpage": handle_open_webpage,
}

# --- WebSocket Handler ---
@sock.route('/api/chat_ws')
def chat_ws(ws):
    global gemini_conversation_history
    last_activity_time = time.time()
    server_ping_interval = 30 # seconds for server to ping client
    client_receive_timeout = 5 # seconds to wait for client message before server pings

    try:
        while True:
            current_time = time.time()
            raw_data = None
            try:
                # Receive data from client with a timeout
                raw_data = ws.receive(timeout=client_receive_timeout)
            except (ConnectionClosed, ConnectionResetError):
                # print("[INFO WebSocket Handler] Connection closed by client (expected).")
                raise # Re-raise to exit the loop and handler
            except Exception: # Catches timeout errors from ws.receive specifically
                # This is expected if client is idle, server will then ping
                pass 

            if raw_data is not None:
                last_activity_time = current_time # Update activity time on receiving data
                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError:
                    print(f"ERREUR: Données WebSocket non JSON reçues: {raw_data}")
                    ws.send(json.dumps({"type": "error", "message": "Invalid JSON."}))
                    continue

                current_user_parts_for_gemini = []
                user_text = data.get('text', '')

                if user_text:
                    current_user_parts_for_gemini.append(user_text)

                # Handle file attachments from client
                file_data_from_client = data.get('fileData')
                file_name_from_client = data.get('fileName')
                file_type_from_client = data.get('fileType') # 'image' or 'text'

                if file_data_from_client and file_name_from_client and file_type_from_client:
                    if file_type_from_client == 'image':
                        try:
                            # Assuming file_data_from_client is a base64 data URL
                            header, encoded = file_data_from_client.split(",", 1)
                            image_bytes = base64.b64decode(encoded)
                            img = Image.open(io.BytesIO(image_bytes))
                            MAX_SIZE = (1024, 1024) # Définissez une taille maximale appropriée
                            img.thumbnail(MAX_SIZE, Image.Resampling.LANCZOS)
                            # Add a textual description and the image object for Gemini
                            current_user_parts_for_gemini.append(f"L'utilisateur a joint une image nommée '{file_name_from_client}'. Voici l'image :")
                            current_user_parts_for_gemini.append(img)
                        except Exception as e:
                            print(f"Erreur lors du décodage de l'image jointe '{file_name_from_client}': {e}")
                            current_user_parts_for_gemini.append(f"(Erreur: Impossible de traiter l'image jointe '{file_name_from_client}')")
                    elif file_type_from_client == 'text':
                        text_content = file_data_from_client # Already text content
                        current_user_parts_for_gemini.append(f"L'utilisateur a joint un fichier texte nommé '{file_name_from_client}'. Voici son contenu :\n```\n{text_content}\n```")
                    else:
                        print(f"WARN: Type de fichier joint non supporté '{file_type_from_client}' pour '{file_name_from_client}'.")
                        current_user_parts_for_gemini.append(f"(Note: Fichier '{file_name_from_client}' de type non supporté '{file_type_from_client}' reçu mais non traité.)")
                
                # Handle webcam image data if no file is attached (file takes precedence)
                elif data.get('imageData'): # imageData is from webcam
                    image_data_url = data.get('imageData')
                    try:
                        header, encoded = image_data_url.split(",", 1)
                        image_bytes = base64.b64decode(encoded)
                        img = Image.open(io.BytesIO(image_bytes))
                        MAX_SIZE = (1024, 1024) # Définissez une taille maximale appropriée
                        img.thumbnail(MAX_SIZE, Image.Resampling.LANCZOS)
                        current_user_parts_for_gemini.append("L'utilisateur a fourni une image via la webcam. Voici l'image :")
                        current_user_parts_for_gemini.append(img)
                    except Exception as e:
                        print(f"Erreur lors du décodage de l'image webcam: {e}")
                        current_user_parts_for_gemini.append("(Erreur: Impossible de traiter l'image de la webcam)")
                
                # --- Initialize response variables ---
                final_text_response_for_action = None # Result from action dispatcher (data for panel)
                action_taken_by_nlu = False 
                parsed_command_action = None 
                chat_display_message = None # What EVA says in chat (witty summary or general response)
                panel_data_content = None 
                panel_target_id = None 
                gemini_explanation_text = None # Text from Gemini (potentially the witty summary)
                extracted_code_block = None  

                # --- Process with Gemini ---
                if not current_user_parts_for_gemini and not gemini_conversation_history:
                    chat_display_message = "Veuillez fournir une requête ou une image."
                else:
                    gemini_raw_response = get_gemini_response(current_user_parts_for_gemini)
                    
                    extracted_json_command_str = None
                    # Default gemini_explanation_text to the full response, it will be refined if JSON is found
                    gemini_explanation_text = str(gemini_raw_response) 

                    if isinstance(gemini_raw_response, str):
                        match_markdown_json = re.search(r"```json\s*(\{.*?\})\s*```", gemini_raw_response, re.DOTALL | re.IGNORECASE)
                        if match_markdown_json:
                            extracted_json_command_str = match_markdown_json.group(1).strip()
                            pre_text = gemini_raw_response[:match_markdown_json.start()].strip()
                            post_text = gemini_raw_response[match_markdown_json.end():].strip()
                            gemini_explanation_text = f"{pre_text}\n{post_text}".strip() if (pre_text or post_text) else None
                        elif gemini_raw_response.strip().startswith("{") and gemini_raw_response.strip().endswith("}"):
                            try:
                                test_parse = json.loads(gemini_raw_response.strip())
                                if isinstance(test_parse, dict) and "action" in test_parse: 
                                    extracted_json_command_str = gemini_raw_response.strip()
                                    gemini_explanation_text = None 
                            except json.JSONDecodeError:
                                pass 

                        if not extracted_json_command_str:
                            match_code = re.search(r"```(?:\w*\s*\n)?([\s\S]*?)\n```", gemini_raw_response, re.DOTALL)
                            if match_code:
                                extracted_code_block = match_code.group(1).strip()
                                pre_text = gemini_raw_response[:match_code.start()].strip()
                                post_text = gemini_raw_response[match_code.end():].strip()
                                if pre_text or post_text:
                                     gemini_explanation_text = f"{pre_text}\n{post_text}".strip()
                                else: 
                                     gemini_explanation_text = "Code généré." 
                                if not gemini_explanation_text.strip(): 
                                     gemini_explanation_text = "Code généré et affiché dans l'onglet Code."


                    # --- Execute Action or Handle Text Response ---
                    parsed_command_obj = None
                    if extracted_json_command_str:
                        try:
                            parsed_command_obj = json.loads(extracted_json_command_str)
                        except json.JSONDecodeError:
                            print(f"WARN: Extracted JSON string failed to parse: {extracted_json_command_str}")
                            # If JSON parsing fails, gemini_explanation_text (the full raw response) will be used as chat_display_message later
                            if gemini_explanation_text is None : gemini_explanation_text = str(gemini_raw_response)


                    if parsed_command_obj and isinstance(parsed_command_obj, dict) and "action" in parsed_command_obj:
                        parsed_command_action = parsed_command_obj.get("action", "").strip()
                        entities = parsed_command_obj.get("entities", {})
                        
                        if parsed_command_action in action_dispatcher:
                            final_text_response_for_action = action_dispatcher[parsed_command_action](entities) # This is data for the panel or a direct status message
                            action_taken_by_nlu = True
                            
                            # CHAT DISPLAY MESSAGE: Prioritize Gemini's witty commentary
                            if gemini_explanation_text and gemini_explanation_text.strip():
                                chat_display_message = gemini_explanation_text.strip()
                            else: # Fallback if Gemini provides no separate explanation
                                if isinstance(final_text_response_for_action, dict) and "summary" in final_text_response_for_action:
                                    chat_display_message = final_text_response_for_action["summary"] # e.g. directions summary
                                else:
                                    chat_display_message = str(final_text_response_for_action) # e.g. "Tâche ajoutée"

                            # PANEL DATA LOGIC: Always use final_text_response_for_action for panel content
                            panel_data_content = None 
                            panel_target_id = None    

                            if parsed_command_action == "list_calendar_events":
                                panel_data_content = str(final_text_response_for_action)
                                panel_target_id = "calendarContent"
                                if not (gemini_explanation_text and gemini_explanation_text.strip()): # Fallback chat message if no wit
                                    chat_display_message = "Voici vos événements." if "Aucun événement" not in str(final_text_response_for_action) else str(final_text_response_for_action)
                            elif parsed_command_action == "list_emails": 
                                panel_data_content = str(final_text_response_for_action)
                                panel_target_id = "emailContent"
                                if not (gemini_explanation_text and gemini_explanation_text.strip()):
                                    chat_display_message = "Voici vos e-mails non lus." if "Aucun e-mail non lu" not in str(final_text_response_for_action) else str(final_text_response_for_action)
                            elif parsed_command_action == "get_contact_emails": 
                                panel_data_content = str(final_text_response_for_action)
                                panel_target_id = "emailContent"
                                if not (gemini_explanation_text and gemini_explanation_text.strip()):
                                    mode = entities.get("retrieve_mode", "summary")
                                    contact_id = entities.get("contact_identifier", "le contact")
                                    if "Aucun email trouvé" in panel_data_content or "non trouvé" in panel_data_content.lower():
                                        chat_display_message = panel_data_content
                                    elif mode == "full_last":
                                        chat_display_message = f"Voici le dernier email de {contact_id}."
                                    else: 
                                        chat_display_message = f"Voici les emails pour {contact_id}."
                            elif parsed_command_action == "list_tasks":
                                panel_data_content = str(final_text_response_for_action)
                                panel_target_id = "taskContent"
                                if not (gemini_explanation_text and gemini_explanation_text.strip()):
                                    chat_display_message = "Voici la liste des tâches." if "Aucune tâche active" not in str(final_text_response_for_action) else str(final_text_response_for_action)
                            elif parsed_command_action == "list_contacts":
                                panel_data_content = str(final_text_response_for_action)
                                panel_target_id = "searchContent" 
                                if not (gemini_explanation_text and gemini_explanation_text.strip()):
                                    chat_display_message = "Voici la liste de vos contacts." if "carnet d'adresses est vide" not in str(final_text_response_for_action) else str(final_text_response_for_action)
                            
                            elif parsed_command_action == "get_directions":
                                if isinstance(final_text_response_for_action, dict): # Expected structure
                                    panel_data_content = final_text_response_for_action.get("summary", "Détails de l'itinéraire non disponibles.")
                                    panel_target_id = "mapContent"
                                    
                                    # Format chat_display_message for directions
                                    if final_text_response_for_action.get("status") == "success":
                                        distance = final_text_response_for_action.get("distance", "distance inconnue")
                                        duration = final_text_response_for_action.get("duration", "durée inconnue")
                                        destination_entity = entities.get("destination", "votre destination")
                                        
                                        # If chat_display_message came from Gemini's explanation (already set), try to format it
                                        if chat_display_message and "{destination}" in chat_display_message: # Check for placeholder
                                            try:
                                                chat_display_message = chat_display_message.format(distance=distance, duration=duration, destination=destination_entity)
                                            except KeyError:
                                                print(f"WARN: Placeholders non trouvés ou incorrects dans chat_display_message (venant de Gemini) pour get_directions. Message: '{chat_display_message}'")
                                                # Fallback: append details to Gemini's text if formatting failed
                                                chat_display_message = f"{chat_display_message.strip()} (Trajet vers {destination_entity}: {distance}, environ {duration})."
                                        else: # No Gemini explanation with placeholders, or it was an error message. Create/use default.
                                            if gemini_explanation_text and gemini_explanation_text.strip(): # Gemini provided text, but not with placeholders for formatting
                                                chat_display_message = f"{gemini_explanation_text.strip()} Le trajet vers {destination_entity} est de {distance} et durera environ {duration}."
                                            else: # No Gemini explanation at all, create a default formatted message
                                                chat_display_message = f"Voici l'itinéraire pour {destination_entity}. Le trajet est de {distance} et durera environ {duration}."
                                    # else: chat_display_message is already an error summary from Gemini or fallback
                                
                                elif isinstance(final_text_response_for_action, str): # Error string from handler
                                    panel_data_content = final_text_response_for_action
                                    panel_target_id = "mapContent"
                                    # chat_display_message would have been set to this string if no gemini_explanation_text
                                    if not (gemini_explanation_text and gemini_explanation_text.strip()):
                                        chat_display_message = final_text_response_for_action
                            
                            elif parsed_command_action == "web_search":
                                panel_data_content = str(final_text_response_for_action)
                                panel_target_id = "searchContent"
                                if not (gemini_explanation_text and gemini_explanation_text.strip()):
                                    query_entity = parsed_command_obj.get("entities", {}).get("query", "votre recherche")
                                    chat_display_message = f"Voici les résultats de recherche pour '{query_entity}'." if "Aucun résultat pertinent" not in str(final_text_response_for_action) else str(final_text_response_for_action)
                            elif parsed_command_action == "get_weather_forecast":
                                panel_data_content = str(final_text_response_for_action) 
                                panel_target_id = "weatherForecastContent" 
                                if not (gemini_explanation_text and gemini_explanation_text.strip()):
                                    chat_display_message = "Voici les prévisions météo."
                            elif parsed_command_action == "execute_python_code":
                                panel_data_content = str(final_text_response_for_action)
                                panel_target_id = "codeDisplayContent"
                                if not (gemini_explanation_text and gemini_explanation_text.strip()):
                                    chat_display_message = "Résultat de l'exécution du code Python (voir onglet Code)."
                            elif parsed_command_action == "generate_3d_object":
                                panel_data_content = str(final_text_response_for_action)
                                panel_target_id = "codeDisplayContent"
                                if not (gemini_explanation_text and gemini_explanation_text.strip()):
                                    chat_display_message = "Code OpenSCAD généré (voir onglet Code)."
                            # For launch_application and open_webpage, panel_data_content remains None.
                            # chat_display_message is already set to the handler's response or Gemini's text.
                            # No specific panel target needed for these two.

                        else: 
                            print(f"WARN [chat_ws] Extracted JSON action not recognized: '{parsed_command_action}'")
                            chat_display_message = gemini_explanation_text if gemini_explanation_text is not None else "Action non reconnue."
                            action_taken_by_nlu = False 
                    
                    elif extracted_code_block: 
                        action_taken_by_nlu = False 
                        parsed_command_action = "code_generation" 
                        panel_data_content = extracted_code_block 
                        panel_target_id = "codeDisplayContent"   
                        chat_display_message = gemini_explanation_text if gemini_explanation_text and gemini_explanation_text.strip() else "Code généré et affiché dans l'onglet Code."
                    
                    else: # No command, no code -> general conversation or Gemini failed to provide JSON + text as instructed
                        action_taken_by_nlu = False
                        chat_display_message = gemini_explanation_text if gemini_explanation_text is not None else "Je n'ai pas compris la demande."


                # --- Prepare and Send Response to Client ---
                if chat_display_message is None: 
                    chat_display_message = "Je ne suis pas sûr de pouvoir traiter cette demande."
                
                chat_display_message = str(chat_display_message) 
                # Clean up potential JSON remnants in chat_display_message if it was supposed to be panel content
                if "```json" in chat_display_message and panel_target_id:
                    if gemini_explanation_text and gemini_explanation_text.strip() and extracted_json_command_str and extracted_json_command_str in gemini_raw_response:
                         chat_display_message = gemini_explanation_text.strip() if gemini_explanation_text.strip() else "Action effectuée."
                    elif extracted_code_block : 
                         chat_display_message = gemini_explanation_text if gemini_explanation_text and gemini_explanation_text.strip() else "Code affiché dans le panneau dédié."
                    else: 
                        chat_display_message = f"Action traitée. Contenu affiché dans le panneau dédié."


                message_to_send = {"type": "final_text", "text": chat_display_message}
                if panel_data_content and panel_target_id:
                    message_to_send["panel_data"] = panel_data_content
                    message_to_send["panel_target_id"] = panel_target_id
                
                ws.send(json.dumps(message_to_send))
                
                # --- TTS Logic ---
                audio_data_url = None
                text_for_gtts = chat_display_message # Base: speak what's in the chat

                if action_taken_by_nlu: # Uniquement si une action NLU a été exécutée
                    if parsed_command_action == "get_directions":
                        if isinstance(final_text_response_for_action, dict) and final_text_response_for_action.get("status") == "success":
                            distance = final_text_response_for_action.get("distance", "distance inconnue")
                            duration = final_text_response_for_action.get("duration", "durée inconnue")
                            destination_entity = entities.get("destination", "votre destination") 

                            # text_for_gtts is already chat_display_message (which should now be formatted)
                            # If chat_display_message was formatted, TTS will use it.
                            # If formatting failed for chat_display_message and it still contains placeholders,
                            # this TTS specific formatting acts as a final fallback for voice.
                            if "{destination}" in text_for_gtts: # Check if formatting is still needed for TTS
                                try:
                                    text_for_gtts = text_for_gtts.format(distance=distance, duration=duration, destination=destination_entity)
                                except KeyError:
                                    print(f"WARN: Placeholders non trouvés ou incorrects dans text_for_gtts pour get_directions. Message: '{text_for_gtts}'")
                                    # Fallback for TTS if chat_display_message formatting also failed
                                    text_for_gtts = f"Pour aller à {destination_entity}, le trajet est de {distance} et durera environ {duration}."
                        elif isinstance(final_text_response_for_action, dict) and final_text_response_for_action.get("summary"):
                            text_for_gtts = final_text_response_for_action["summary"] # Error or not_found summary for TTS

                    elif not (gemini_explanation_text and gemini_explanation_text.strip()):
                        if parsed_command_action == "create_calendar_event" and "ajouté à votre calendrier" in chat_display_message.lower():
                            text_for_gtts = "Événement ajouté au calendrier." 
                        elif parsed_command_action == "web_search" and panel_target_id == "searchContent":
                            text_for_gtts = "Voici les résultats de recherche."
                        elif parsed_command_action == "list_contacts" and panel_target_id == "searchContent":
                            text_for_gtts = "Voici la liste des contacts."
                        elif parsed_command_action == "list_tasks" and panel_target_id == "taskContent":
                            text_for_gtts = "Voici la liste des tâches."
                        elif parsed_command_action == "list_calendar_events" and panel_target_id == "calendarContent":
                             text_for_gtts = "Voici les événements du calendrier."
                        elif parsed_command_action == "execute_python_code" and "ATTENTION" in chat_display_message:
                             text_for_gtts = "Le code Python a été exécuté. Vérifiez les résultats."
                        elif parsed_command_action == "generate_3d_object":
                             text_for_gtts = "J'ai généré le code OpenSCAD pour votre objet."
                        # For launch_application and open_webpage, chat_display_message is already the status.


                elif parsed_command_action == "code_generation" and panel_target_id == "codeDisplayContent" and extracted_code_block:
                     text_for_gtts = gemini_explanation_text if gemini_explanation_text and gemini_explanation_text.strip() else "Voici le code que j'ai généré."
                
                should_speak = True 
                lower_chat_message_for_tts_check = text_for_gtts.lower()

                suppress_audio_keywords = [
                     "client gemini non configuré", "réponse gemini bloquée",
                     "erreur critique", "erreur serveur", "erreur interne",
                     "bibliothèque manquante", "non disponible",
                     "je ne suis pas sûr de comprendre votre demande" , 
                ]
                if any(keyword in lower_chat_message_for_tts_check for keyword in suppress_audio_keywords):
                    if text_for_gtts == chat_display_message: 
                            should_speak = False
                
                if text_for_gtts.strip() == "" or lower_chat_message_for_tts_check == "ok.": 
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
                        # print(f"DEBUG: Server PING to client at {current_time}")
                        ws.send(json.dumps({"type": "system_ping", "timestamp": current_time}))
                        last_activity_time = current_time 
                    except (ConnectionClosed, ConnectionResetError):
                        # print("[INFO WebSocket Handler] Connection closed by client during ping (expected).")
                        raise 
                    except Exception as e_ping:
                        print(f"ERREUR lors de l'envoi du ping serveur: {type(e_ping).__name__} - {e_ping}")
                        traceback.print_exc()
                        raise 

    except (ConnectionClosed, ConnectionResetError):
        print(f"[INFO WebSocket Handler] Connexion fermée avec le client.")
    except Exception as e:
        print(f"[ERREUR WebSocket Handler Critique] /api/chat_ws: {type(e).__name__} - {e}")
        traceback.print_exc()
        try:
            if ws and hasattr(ws, 'connected') and ws.connected: # Check if ws is defined and connected
                 ws.send(json.dumps({"type": "error", "message": f"Erreur serveur: {type(e).__name__}"}))
        except Exception as send_error:
            print(f"Impossible d'envoyer le message d'erreur final au client: {send_error}")
    finally:
        print(f"[INFO WebSocket Handler] Fin du handler pour un client.")


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
