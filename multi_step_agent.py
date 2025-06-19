# multi_step_agent.py
import os
import sys
import json
import traceback
import re
import requests  # Pour les appels HTTP (recherche et contenu de page)
import urllib3   # Pour la gestion des avertissements SSL
from bs4 import BeautifulSoup # Pour parser le HTML
import io
import contextlib
import subprocess
import googlemaps # Ajouté pour le géocodage
import urllib.parse
# Nouveaux imports pour l'analyse d'images et de documents
from PIL import Image
import PyPDF2
from io import BytesIO
from email.message import EmailMessage


import base64
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import google.generativeai as genai
from dotenv import load_dotenv

# Supprime les avertissements de requêtes HTTPS non vérifiées (InsecureRequestWarning)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Force la sortie standard en UTF-8 pour éviter les erreurs de décodage Unicode sous Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- Configuration ---
load_dotenv()
# Assurez-vous que la clé API pour ce modèle est bien définie
gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    print(json.dumps({"type": "error", "content": "Clé API Gemini manquante pour l'agent."}), flush=True)
    sys.exit(1)
# --- NOUVEAU: Configuration pour Gmail ---
gmail_token_path = os.getenv("GMAIL_TOKEN_PICKLE_PATH")
gmail_scopes = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify'
]

gmail_enabled = bool(gmail_token_path) and os.path.exists('credentials.json')
# --- Configuration pour Google APIs ---
google_custom_search_api_key = os.getenv("GOOGLE_CUSTOM_SEARCH_API_KEY")
google_custom_search_cx = os.getenv("GOOGLE_CUSTOM_SEARCH_CX")
Maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY") # NOUVEAU: Clé pour Maps

google_search_enabled = bool(google_custom_search_api_key and google_custom_search_cx)
Maps_enabled = bool(Maps_api_key) # NOUVEAU: Flag pour Maps

genai.configure(api_key=gemini_api_key)
# Utilisation d'un modèle apte au raisonnement complexe et à l'utilisation d'outils
agent_model = genai.GenerativeModel('gemini-2.0-flash-lite')

# --- Boîte à Outils de l'Agent ---

def web_search(query: str, num_results: int = 5) -> str:
    """
    Effectue une recherche web en utilisant l'API Google Custom Search et retourne les résultats.
    """
    if not google_search_enabled:
        return "Erreur: Le service de recherche web n'est pas configuré. Veuillez vérifier les variables GOOGLE_CUSTOM_SEARCH_API_KEY et GOOGLE_CUSTOM_SEARCH_CX dans le fichier .env."

    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            'key': google_custom_search_api_key,
            'cx': google_custom_search_cx,
            'q': query,
            'num': num_results,
            'hl': 'fr', # Recherche en français
            'gl': 'fr'  # Géolocalisation des résultats en France
        }
        response = requests.get(url, params=params)
        response.raise_for_status()  # Lève une exception pour les codes d'erreur HTTP
        search_results = response.json()

        items = search_results.get("items", [])
        if not items:
            return f"Aucun résultat de recherche trouvé pour '{query}'."

        output = ""
        for i, item in enumerate(items):
            title = item.get("title", "Sans titre")
            snippet = item.get("snippet", "Pas d'extrait disponible.").replace('\n', ' ')
            link = item.get("link", "#")
            output += f"{i+1}. {title}\n   Extrait: {snippet}\n   Source: {link}\n\n"

        return output.strip()

    except requests.exceptions.RequestException as e:
        return f"Erreur de réseau ou d'API lors de la recherche web : {e}"
    except Exception as e:
        return f"Erreur inattendue lors de la recherche web : {e}"

def view_webpage(url: str) -> str:
    """
    Récupère et extrait le contenu textuel d'une page web HTML à partir de son URL.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        # Ajout de verify=False pour ignorer les erreurs de certificat SSL
        response = requests.get(url, headers=headers, timeout=15, verify=False)
        response.raise_for_status()
        
        content_type = response.headers.get('content-type', '').lower()
        # Redirige vers le bon outil si l'URL est un PDF ou un TXT
        if 'application/pdf' in content_type or url.lower().endswith('.pdf'):
            return "Erreur: L'URL pointe vers un fichier PDF. Veuillez utiliser l'outil 'read_document' pour en lire le contenu."
        if 'text/plain' in content_type or url.lower().endswith('.txt'):
            return "Erreur: L'URL pointe vers un fichier TXT. Veuillez utiliser l'outil 'read_document' pour en lire le contenu."

        # Utilise BeautifulSoup pour parser le HTML
        soup = BeautifulSoup(response.content, 'html.parser')

        # Supprime les balises de script et de style qui ne contiennent pas de contenu visible
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()

        # Extrait le texte
        text = soup.get_text(separator='\n', strip=True)
        
        # Réduit les lignes vides multiples pour une meilleure lisibilité
        cleaned_text = re.sub(r'\n\s*\n+', '\n', text)

        # Limite la longueur pour éviter de surcharger le prompt
        max_length = 8000
        if len(cleaned_text) > max_length:
            return cleaned_text[:max_length] + "\n\n[Contenu tronqué en raison de la longueur]"

        return cleaned_text if cleaned_text else "Le contenu de la page est vide ou n'a pas pu être extrait."

    except requests.exceptions.RequestException as e:
        return f"Erreur de réseau ou HTTP lors de la récupération de la page : {e}"
    except Exception as e:
        return f"Erreur inattendue lors de l'analyse de la page web : {e}"

def read_document_from_url(url: str) -> str:
    """
    Lit le contenu d'un fichier PDF ou TXT à partir d'une URL.
    Nécessite l'installation de 'PyPDF2' (pip install PyPDF2).
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        # Ajout de verify=False pour ignorer les erreurs de certificat SSL, comme pour les pages web.
        response = requests.get(url, headers=headers, timeout=20, verify=False)
        response.raise_for_status()

        content_type = response.headers.get('content-type', '').lower()
        is_pdf = 'application/pdf' in content_type or url.lower().endswith('.pdf')
        is_txt = 'text/plain' in content_type or url.lower().endswith('.txt')

        if is_pdf:
            # Utilise un flux en mémoire pour lire le contenu du PDF
            pdf_file = BytesIO(response.content)
            reader = PyPDF2.PdfReader(pdf_file)
            text = ""
            for page in reader.pages:
                # Ajoute le texte de chaque page, en gérant les cas où l'extraction ne retourne rien
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text.strip() if text.strip() else "Le contenu du PDF est vide ou n'a pas pu être extrait."
        
        elif is_txt:
            # Décode le contenu texte en utilisant l'encodage détecté par requests
            return response.text

        else:
            return "Erreur: L'URL ne semble pointer ni vers un PDF, ni vers un fichier TXT. Pour une page web HTML, utilisez l'outil 'view_webpage'."

    except requests.exceptions.RequestException as e:
        return f"Erreur de réseau lors de la récupération du document : {e}"
    except PyPDF2.errors.PdfReadError:
        return "Erreur: Le fichier à l'URL indiquée n'est pas un PDF valide ou est corrompu."
    except Exception as e:
        # Capture toute autre erreur inattendue
        return f"Erreur inattendue lors de la lecture du document : {e}"

def analyze_image(url: str, question: str = "Décris cette image en détail. Si c'est une personne, essaie de l'identifier si c'est une célébrité.") -> str:
    """
    Analyse une image à partir d'une URL. Télécharge l'image, puis utilise un modèle
    multimodal pour répondre à une question à son sujet ou pour la décrire.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15, verify=False)
        response.raise_for_status()
        
        content_type = response.headers.get('content-type', '')
        if not content_type.startswith('image/'):
            return f"Erreur: L'URL ne semble pas pointer vers une image. Type de contenu: {content_type}"

        image_bytes = io.BytesIO(response.content)
        image = Image.open(image_bytes)

        # Utiliser un modèle multimodal pour l'analyse.
        vision_model = genai.GenerativeModel('gemini-2.0-flash')
        prompt_parts = [question, image]
        
        vision_response = vision_model.generate_content(prompt_parts)
        return vision_response.text

    except requests.exceptions.RequestException as e:
        return f"Erreur de réseau lors de la récupération de l'image: {e}"
    except Exception as e:
        return f"Erreur inattendue lors de l'analyse de l'image: {e}"

def execute_python(code: str) -> str:
    """
    Exécute un bloc de code Python et retourne sa sortie standard (stdout) et son erreur standard (stderr).
    """
    code_to_execute = code.strip()
    output_capture = io.StringIO()
    error_capture = io.StringIO()

    try:
        with contextlib.redirect_stdout(output_capture), contextlib.redirect_stderr(error_capture):
            exec(code_to_execute, {})
        stdout_val = output_capture.getvalue()
        stderr_val = error_capture.getvalue()
        response = ""
        if stdout_val:
            response += f"Sortie standard:\n---\n{stdout_val}\n---\n"
        if stderr_val:
            response += f"Erreur standard:\n---\n{stderr_val}\n---\n"
        if not stdout_val and not stderr_val:
            response = "Le code a été exécuté avec succès sans produire de sortie."
        return response.strip()
    except Exception as e:
        return f"Erreur lors de l'exécution du code:\n{traceback.format_exc()}"

def play_fl_studio_sequence(sequence_json: str) -> str:
    """
    Joue une séquence de notes ou d'accords sur FL Studio.
    Le paramètre 'sequence_json' doit être une chaîne de caractères contenant un JSON valide
    qui représente une liste d'événements musicaux.
    """
    try:
        controller_path = "fl_studio_controller.py"
        if not os.path.exists(controller_path):
            return "Erreur : Le script 'fl_studio_controller.py' est introuvable."

        try:
            json.loads(sequence_json)
        except json.JSONDecodeError:
            return "Erreur : le paramètre 'sequence_json' n'est pas une chaîne JSON valide."

        command = [sys.executable, controller_path, sequence_json]
        subprocess.Popen(command)

        return f"La séquence musicale a été envoyée à FL Studio."
    except Exception as e:
        return f"Erreur lors du lancement de la séquence musicale : {e}"

def locate_on_map(location_name: str) -> str:
    """
    Trouve les coordonnées géographiques d'un lieu donné et retourne un objet JSON
    pour l'afficher sur une carte.
    """
    if not Maps_enabled:
        return json.dumps({"type": "error", "content": "La clé API Google Maps n'est pas configurée."})

    try:
        gmaps = googlemaps.Client(key=Maps_api_key)
        geocode_result = gmaps.geocode(location_name, language='fr')

        if not geocode_result:
            return json.dumps({"type": "error", "content": f"Impossible de trouver le lieu : {location_name}"})

        first_result = geocode_result[0]
        location_data = {
            "name": first_result.get("formatted_address", location_name),
            "lat": first_result["geometry"]["location"]["lat"],
            "lng": first_result["geometry"]["location"]["lng"]
        }
        
        # Retourne un objet JSON structuré que le frontend peut interpréter
        return json.dumps({
            "type": "map_location",
            "location": location_data
        })
    except Exception as e:
        return json.dumps({"type": "error", "content": f"Erreur API Google Maps: {e}"})

def get_street_view_image(latitude: float, longitude: float, heading: int = 0, pitch: int = 0, fov: int = 90) -> str:
    """
    Obtient une image statique de Google Street View pour des coordonnées géographiques données.
    Retourne un objet JSON contenant l'URL de l'image et une légende.
    """
    if not Maps_enabled:
        return json.dumps({"type": "error", "content": "La clé API Google Maps n'est pas configurée."})

    try:
        base_url = "https://maps.googleapis.com/maps/api/streetview"
        params = {
            'size': '600x400',
            'location': f'{latitude},{longitude}',
            'heading': heading,
            'pitch': pitch,
            'fov': fov,
            'key': Maps_api_key
        }
        
        image_url = f"{base_url}?{urllib.parse.urlencode(params)}"
        
        return json.dumps({
            "type": "image",
            "url": image_url,
            "caption": f"Aperçu Street View pour les coordonnées ({latitude:.4f}, {longitude:.4f})"
        })
        
    except Exception as e:
        return json.dumps({"type": "error", "content": f"Erreur API Street View: {e}"})    

def get_gmail_service():
    """
    Crée et retourne un service Gmail API authentifié. Gère le flux OAuth2.
    """
    creds = None
    if os.path.exists(gmail_token_path):
        creds = Credentials.from_authorized_user_file(gmail_token_path, gmail_scopes)
    
    # Si les identifiants n'existent pas ou sont invalides, lancez le flux d'authentification.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', gmail_scopes)
            creds = flow.run_local_server(port=0)
        
        # Sauvegarde les identifiants pour la prochaine exécution
        with open(gmail_token_path, 'w') as token:
            token.write(creds.to_json())
            
    return build('gmail', 'v1', credentials=creds)

def send_email(to: str, subject: str, body: str) -> str:
    """
    Version finale qui répare les chaînes de caractères d'entrée en les
    transcodant de cp1252 (probable source de l'erreur) vers UTF-8.
    """
    if not gmail_enabled:
        return "Erreur: La fonctionnalité Gmail n'est pas configurée..."

    try:
        # --- BLOC DE RÉPARATION DE CHAÎNE ---
        # Cette astuce "encode/decode" force la réinterprétation des caractères.
        # On suppose que la source était du texte Windows (cp1252) mal interprété.
        try:
            # On encode en bytes selon une carte 1-pour-1 (latin-1) puis on décode
            # en utilisant le codec que l'on suppose être le bon (cp1252).
            subject_repaired = subject.encode('latin-1').decode('cp1252')
            body_repaired = body.encode('latin-1').decode('cp1252')
        except (UnicodeEncodeError, UnicodeDecodeError):
            # Si la réparation échoue, on se rabat sur le remplacement sécurisé.
            subject_repaired = subject.encode('utf-8', errors='replace').decode('utf-8')
            body_repaired = body.encode('utf-8', errors='replace').decode('utf-8')
        # --- FIN DU BLOC DE RÉPARATION ---

        service = get_gmail_service()
        
        message = EmailMessage()
        message.set_content(body_repaired) # On utilise la version réparée
        
        message['To'] = to
        message['From'] = 'me'
        message['Subject'] = subject_repaired # On utilise la version réparée
        
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}
        
        send_message = (service.users().messages().send(userId="me", body=create_message).execute())
        return f"E-mail envoyé avec succès à {to}. ID du message: {send_message['id']}"

    except HttpError as error:
        return f"Erreur API lors de l'envoi de l'e-mail: {error}"
    except Exception as e:
        return f"Erreur inattendue lors de l'envoi de l'e-mail: {e}"

def read_inbox(query: str = "is:unread in:inbox", max_results: int = 5) -> str:
    """
    Lit les e-mails de la boîte de réception correspondant à une requête.
    Exemples de requêtes : 'from:paypal', 'subject:facture', 'is:unread'.
    """
    if not gmail_enabled:
        return "Erreur: La fonctionnalité Gmail n'est pas configurée."
        
    try:
        service = get_gmail_service()
        results = service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
        messages = results.get('messages', [])

        if not messages:
            return f"Aucun message trouvé pour la requête : '{query}'."

        email_summaries = []
        for msg in messages:
            msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
            payload = msg_data['payload']
            headers = payload.get('headers', [])
            
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'Sans objet')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Inconnu')
            
            snippet = msg_data.get('snippet', 'Pas d\'extrait.')
            email_summaries.append(f"De: {sender}\nObjet: {subject}\nExtrait: {snippet}\n---")
            
        return "\n".join(email_summaries)

    except HttpError as error:
        return f"Erreur lors de la lecture de la boîte de réception: {error}"
    except Exception as e:
        return f"Erreur inattendue lors de la lecture des e-mails: {e}"
    
def summarize_webpage(url: str, topic: str = "les points clés") -> str:
    """
    Récupère, nettoie et résume le contenu d'une page web.
    Utilise cet outil pour obtenir un résumé concis d'un article avant de l'envoyer par e-mail ou de l'analyser.
    Retourne uniquement le résumé textuel.
    """
    try:
        # Étape 1 : Récupérer le contenu de la page (similaire à view_webpage)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15, verify=False)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        for script_or_style in soup(["script", "style", "nav", "footer", "header"]):
            script_or_style.decompose()
        
        text = soup.get_text(separator='\n', strip=True)
        cleaned_text = re.sub(r'\n\s*\n+', '\n', text)

        if not cleaned_text:
            return "Erreur : Le contenu de la page est vide ou n'a pas pu être extrait."

        # Limite la longueur pour le prompt de résumé
        max_length = 12000
        truncated_text = cleaned_text[:max_length]

        # Étape 2 : Appeler un modèle pour effectuer le résumé
        summarizer_model = genai.GenerativeModel('gemini-2.0-flash-lite')
        prompt = f"Résume le texte suivant en te concentrant sur {topic}. Le résumé doit être concis, informatif et prêt à être envoyé par e-mail :\n\n---\n{truncated_text}\n---"
        
        summary_response = summarizer_model.generate_content(prompt)
        
        return summary_response.text.strip()

    except requests.exceptions.RequestException as e:
        return f"Erreur réseau lors de la récupération de la page pour le résumé : {e}"
    except Exception as e:
        return f"Erreur inattendue lors du résumé de la page : {e}"    

AVAILABLE_TOOLS = {
    "web_search": {
        "function": web_search,
        "description": "Recherche sur le web pour obtenir des informations générales ou des URL. Utiliser pour des questions sur des lieux, des personnes, des événements, etc.",
        "params": {"query": "string", "num_results": "integer (optionnel, défaut 5)"}
    },
    "view_webpage": {
        "function": view_webpage,
        "description": "Extrait le contenu textuel d'une page web HTML. Ne pas utiliser pour les PDF ou TXT. À utiliser après une recherche web pour analyser le contenu d'une page spécifique.",
        "params": {"url": "string (URL complète de la page à lire)"}
    },
    "read_document": {
        "function": read_document_from_url,
        "description": "Lit le contenu textuel d'un document distant (PDF ou TXT) à partir de son URL. Utiliser pour analyser des rapports, des articles ou des documents textes.",
        "params": {"url": "string (URL complète du document PDF ou TXT)"}
    },
    "locate_on_map": {
        "function": locate_on_map,
        "description": "Trouve et affiche un lieu sur une carte. Utilise cet outil lorsque l'utilisateur demande de montrer, localiser ou afficher un endroit.",
        "params": {"location_name": "string (Le nom de la ville, du monument, ou de l'adresse à localiser)"}
    },
    "get_street_view_image": {
        "function": get_street_view_image,
        "description": "Obtient une image statique de Google Street View pour des coordonnées géographiques (latitude, longitude). Utile pour visualiser à quoi ressemble un endroit. Doit être utilisé APRÈS avoir obtenu des coordonnées avec 'locate_on_map'.",
        "params": {
            "latitude": "float (coordonnée de latitude)",
            "longitude": "float (coordonnée de longitude)",
            "heading": "integer (optionnel, direction de la caméra de 0 à 360)",
            "pitch": "integer (optionnel, inclinaison verticale de la caméra de -90 à 90)"}
    },
    "analyze_image": {
        "function": analyze_image,
        "description": "Analyse le contenu d'une image à partir d'une URL. Utilise cet outil pour décrire des images, identifier des objets, du texte, ou des personnes (célébrités) dans une image.",
        "params": {"url": "string (URL complète de l'image)", "question": "string (optionnel, la question spécifique sur l'image)"}
    },
    "python_interpreter": {
        "function": execute_python,
        "description": "Exécute du code Python. Utilise-le pour des calculs complexes, la manipulation de chaînes de caractères, ou pour créer du contenu structuré (ex: HTML, SVG). Le code est exécuté dans un environnement isolé.",
        "params": {"code": "string (doit être un bloc de code Python valide)"}
    },
    "play_music_sequence": {
        "function": play_fl_studio_sequence,
        "description": "Joue une séquence de notes ou d'accords sur FL Studio via le script 'fl_studio_controller.py'. L'agent doit générer lui-même la chaîne JSON de la séquence à jouer.",
        "params": {"sequence_json": "string (une chaîne JSON qui représente une liste d'événements musicaux)"}
    },
    "finish": {
        "function": lambda answer: answer,
        "description": "Utilise cet outil pour terminer la tâche et fournir la réponse finale.",
        "params": {"answer": "string (La réponse finale et complète à la tâche)"}
    },
        "send_email": {
        "function": send_email,
        "description": "Envoie un e-mail à un destinataire spécifié. Utiliser pour communiquer des résultats ou envoyer des informations.",
        "params": {
            "to": "string (l'adresse e-mail du destinataire)",
            "subject": "string (l'objet de l'e-mail)",
            "body": "string (le contenu du corps de l'e-mail)"
        }
    },
        "read_inbox": {
        "function": read_inbox,
        "description": "Consulte la boîte de réception Gmail pour trouver des e-mails récents ou spécifiques en utilisant une requête de recherche. Très utile pour vérifier des notifications ou des réponses.",
        "params": {
            "query": "string (optionnel, requête de recherche type Gmail, ex: 'is:unread', défaut: 'is:unread in:inbox')",
            "max_results": "integer (optionnel, nombre maximum de messages à retourner, défaut: 5)"
        }
    },
        "summarize_webpage": {
        "function": summarize_webpage,
        "description": "Récupère et résume le contenu d'une page web en une seule action. Utilise cet outil pour extraire les points clés d'un article avant de l'envoyer ou de l'analyser. C'est plus efficace que d'utiliser 'view_webpage' puis de résumer mentalement.",
        "params": {
            "url": "string (URL complète de la page à résumer)",
            "topic": "string (optionnel, le sujet sur lequel se concentrer pour le résumé, ex: 'les aspects financiers')"
        }
    },
}


AGENT_SYSTEM_PROMPT = f"""
Tu es un agent autonome intelligent. Ta mission est de résoudre la tâche donnée en utilisant une chaîne de pensée (Thought) et d'action (Action).

# INSTRUCTIONS DE BASE
1.  **Thought**: À chaque étape, réfléchis à la tâche, analyse les informations disponibles, et planifie ta prochaine action. Explique ton raisonnement de manière concise.
2.  **Action**: Choisis UN seul outil parmi ceux disponibles et fournis les paramètres nécessaires.
3.  **Format**: Ta réponse doit être exclusivement en JSON avec les clés "thought" et "action". L'objet "action" doit contenir "tool_name" et "parameters".

# STRATÉGIE ET RAISONNEMENT
- **Décomposition Logique**: Décompose les problèmes complexes en étapes séquentielles. La sortie d'une action alimente la suivante.
- **Utilisation des Données Initiales**:
  - **URL de Page Web HTML**: Si la tâche est d'analyser une page web (texte), ta première action DOIT être `view_webpage` avec l'URL fournie.
  - **URL de Document (PDF/TXT)**: Si la tâche concerne une URL finissant par `.pdf` ou `.txt`, ta première action DOIT être `read_document`.
  - **URL d'Image**: Si la tâche est d'analyser une IMAGE via une URL, ta première action DOIT être `analyze_image`.
- **Gestion des Échecs (Très Important)**:
  - Si un outil échoue (par exemple, avec une erreur réseau 403 ou 429), **NE T'ARRÊTE PAS**. Analyse l'erreur et essaie une autre approche. Par exemple, si `view_webpage` échoue, utilise `web_search` pour trouver une source alternative ou des informations sur le problème.
- **Vérification Critique**: Pour les tâches d'identification (comme trouver un lieu), après avoir une hypothèse, VÉRIFIE-LA. Utilise `web_search` avec le nom du lieu pour trouver d'autres photos et compare-les avec la description initiale. Si ça ne correspond pas, cherche d'autres hypothèses.
- **NOUVEAU - Gestion des Communications**:
  - Utilise l'outil `send_email` lorsque la tâche te demande explicitement de communiquer, de notifier, d'envoyer un rapport ou de transmettre un résultat à quelqu'un.
  - Utilise l'outil `read_inbox` pour vérifier si des informations nouvelles ou attendues (comme une confirmation, une réponse) sont arrivées par e-mail.
- **Exemple de tâche complexe (Géographie) : "Où cette photo a-t-elle été prise ?"**
    1.  **Analyse d'abord l'image** avec `analyze_image` pour extraire des indices uniques.
    2.  **Utilise ces indices** avec `web_search` pour trouver un nom de lieu probable.
    3.  **Vérifie** ce lieu en cherchant d'autres images avec `web_search`.
    4.  Si la vérification est concluante, **convertis le nom en coordonnées** avec `locate_on_map`.
    5.  **Utilise `get_street_view_image`** pour la visualisation finale.
- **NOUVEAU - Exemple de tâche complexe (Recherche et Communication) : "Cherche un article récent sur l'IA puis envoie un résumé à [adresse e-mail du destinataire]"**
    1.  **Commence par la recherche** avec `web_search` en utilisant une requête comme "derniers articles sur l'intelligence artificielle".
    2.  **Analyse la page la plus pertinente** avec `view_webpage` pour en extraire le contenu.
    3.  **Synthétise mentalement** les informations clés de l'article pour créer un résumé.
    4.  **Utilise `send_email`** pour envoyer le résumé généré à l'adresse spécifiée.
- **Réponse Finale**: Lorsque tu as la réponse complète, vérifiée et que toutes les actions requises (comme l'envoi d'un e-mail) sont terminées, utilise l'outil spécial "finish".
- **NOUVELLE RÈGLE CRITIQUE - Gestion des Adresses E-mail**: La valeur spéciale `"me"` dans l'API Gmail fait référence à ton propre compte (celui qui est authentifié). Ne l'utilise **JAMAIS** comme destinataire dans le paramètre `to` de l'outil `send_email`, sauf si la tâche est explicitement de t'envoyer un e-mail à toi-même. Le destinataire doit toujours être extrait de la demande de l'utilisateur.
  **NOUVEAU - Exemple de tâche complexe (Recherche et Communication) : "Cherche un article récent sur l'IA puis envoie un résumé à jeanmichel@exemple.com"
    1.  **Recherche** avec `web_search` pour trouver un article pertinent et obtenir son URL.
    2.  **Utilise le NOUVEL outil `summarize_webpage`** avec l'URL pour obtenir un résumé propre et concis.
    3.  **Valide** le destinataire 'jeanmichel@exemple.com' dans ta pensée.
    4.  **Utilise `send_email`** avec le résumé obtenu à l'étape 2.

# OUTILS DISPONIBLES
{json.dumps({name: {"description": tool["description"], "params": tool["params"]} for name, tool in AVAILABLE_TOOLS.items()}, indent=2, ensure_ascii=False)}
"""

def run_agent_loop(initial_task: str):
    """Exécute la boucle de raisonnement et d'action de l'agent."""
    observation = f"Tâche initiale: {initial_task}"
    history = []
    max_steps = 10

    for step in range(max_steps):
        prompt = f"{AGENT_SYSTEM_PROMPT}\n\n"
        prompt += "--- Historique des étapes précédentes ---\n"
        prompt += "\n".join(history)
        prompt += f"\n\n--- Étape actuelle ---\nObservation: {observation}\n\nTa réponse JSON:"

        try:
            response = agent_model.generate_content(prompt)
            raw_text = response.text

            json_str = raw_text
            match = re.search(r'```json\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
            if match:
                json_str = match.group(1)

            decision_json = json.loads(json_str)
            thought = decision_json.get("thought", "Aucune pensée formulée.")
            action = decision_json.get("action", {})
            tool_name = action.get("tool_name")
            parameters = action.get("parameters", {})
        except Exception as e:
            error_message = f"Erreur lors de la décision de l'agent: {e}\nRéponse brute: {response.text if 'response' in locals() else 'N/A'}"
            print(json.dumps({"type": "error", "content": error_message}, ensure_ascii=False), flush=True)
            break

        print(json.dumps({"type": "thought", "content": thought}, ensure_ascii=False), flush=True)
        history.append(f"Thought: {thought}")

        if not tool_name:
            print(json.dumps({"type": "error", "content": "L'agent n'a pas choisi d'outil."}), flush=True)
            break

        print(json.dumps({"type": "action", "tool": tool_name, "params": parameters}, ensure_ascii=False), flush=True)
        history.append(f"Action: {tool_name} avec params {parameters}")


        if tool_name in AVAILABLE_TOOLS:
            output_capture = io.StringIO()
            error_capture = io.StringIO()
            try:
                if tool_name == 'finish':
                    observation = parameters.get('answer', 'Tâche terminée.')
                    print(json.dumps({"type": "observation", "content": str(observation)}, ensure_ascii=False), flush=True)
                    return # Fin de la boucle

                tool_function = AVAILABLE_TOOLS[tool_name]["function"]
                # Redirige stdout/stderr pour capturer toute sortie parasite des bibliothèques
                with contextlib.redirect_stdout(output_capture), contextlib.redirect_stderr(error_capture):
                    tool_result = tool_function(**parameters)

                stdout_val = output_capture.getvalue()
                stderr_val = error_capture.getvalue()
                
                # Filtre l'avertissement InsecureRequestWarning de la sortie d'erreur
                if "InsecureRequestWarning" in stderr_val:
                    lines = stderr_val.splitlines()
                    filtered_lines = [line for line in lines if "InsecureRequestWarning" not in line]
                    stderr_val = "\n".join(filtered_lines)

                observation = str(tool_result)
                if stdout_val:
                    observation += f"\n\n[Sortie standard capturée]:\n{stdout_val}"
                # N'ajoute la section d'erreur que si stderr_val contient encore quelque chose après le filtrage
                if stderr_val.strip():
                    observation += f"\n\n[Erreur standard capturée]:\n{stderr_val}"

            except Exception as e:
                observation = f"Erreur lors de l'exécution de l'outil '{tool_name}': {e}"
                traceback.print_exc()
        else:
            observation = f"Erreur: Outil '{tool_name}' inconnu."

        print(json.dumps({"type": "observation", "content": str(observation)}, ensure_ascii=False), flush=True)
        history.append(f"Observation: {observation}")

    else:
        print(json.dumps({"type": "error", "content": "L'agent a atteint le nombre maximum d'étapes sans terminer la tâche."}), flush=True)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
        run_agent_loop(task)
    else:
        print(json.dumps({"type": "error", "content": "Aucune tâche fournie à l'agent."}), flush=True)
