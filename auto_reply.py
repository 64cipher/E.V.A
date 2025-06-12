# auto_reply_agent.py (version corrigée et autonome pour l'envoi)

import os
import time
import json
import pickle
import asyncio
import websockets
import argparse
import base64
from email.message import EmailMessage
from email.utils import parseaddr

# --- Bibliothèques Google ---
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ==============================================================================
# --- CONFIGURATION (CORRIGÉE) ---
# ==============================================================================

CONTACTS_TO_MONITOR = [
    "silverdirito@hotmail.fr",
]

# Modifié pour utiliser des préfixes au lieu d'adresses exactes
EXCLUDED_PREFIXES = [
    "noreply@",
    "no-reply@",
    "mailer-daemon@",
]

POLLING_INTERVAL_SECONDS = 7
FLASK_WEBSOCKET_URL = "ws://localhost:5000/api/chat_ws"
CLIENT_SECRETS_FILE = 'client_secret_eva.json' # Non utilisé dans ce script, mais conservé pour référence
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify'
]

# ==============================================================================
# --- FIN DE LA CONFIGURATION ---
# ==============================================================================

processed_message_ids = set()

def get_google_credentials(token_file):
    creds = None
    if os.path.exists(token_file):
        with open(token_file, 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(token_file, 'wb') as token:
                    pickle.dump(creds, token)
            except Exception as e:
                print(f"Erreur lors du rafraîchissement de {token_file} : {e}")
                return None
        else:
            print(f"Aucun identifiant valide trouvé dans {token_file}. Veuillez exécuter le script de génération de jeton.")
            return None
    return creds

def check_for_new_emails(service, reply_all_mode, silent_mode):
    """Vérifie les emails non lus en fonction du mode et applique la liste d'exclusion par préfixe."""
    query = ""
    if reply_all_mode:
        if not silent_mode:
            print("Vérification de TOUS les emails non lus...")
        query = "is:unread"
    else:
        if not CONTACTS_TO_MONITOR:
            if not silent_mode:
                print("Aucun contact à surveiller. Le script ne fera rien.")
            return []
        if not silent_mode:
            print(f"Vérification des emails pour les contacts surveillés...")
        from_query = " OR ".join(CONTACTS_TO_MONITOR)
        query = f"from:({from_query}) is:unread"

    try:
        results = service.users().messages().list(userId='me', q=query).execute()
        messages = results.get('messages', [])
        email_details = []
        if not messages:
            return email_details

        if not silent_mode:
            print(f"  -> {len(messages)} email(s) non lu(s) trouvé(s) initialement.")

        for msg_ref in messages:
            if msg_ref['id'] in processed_message_ids:
                continue
                
            msg = service.users().messages().get(userId='me', id=msg_ref['id'], format='full').execute()
            headers = msg.get('payload', {}).get('headers', [])
            sender_raw = next((h['value'] for h in headers if h['name'].lower() == 'from'), '')
            _, sender_email = parseaddr(sender_raw)
            sender_email_lower = sender_email.lower()

            # --- LOGIQUE CORRIGÉE ---
            # Vérifie si l'email de l'expéditeur commence par un des préfixes exclus.
            is_excluded = any(sender_email_lower.startswith(prefix) for prefix in EXCLUDED_PREFIXES)

            if is_excluded:
                if not silent_mode:
                    print(f"  -> Email de '{sender_email}' ignoré (préfixe d'exclusion).")
                mark_email_as_read(service, msg_ref['id'])
                processed_message_ids.add(msg_ref['id'])
                continue
            # --- FIN DE LA CORRECTION ---

            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'Sans objet')
            message_id_header = next((h['value'] for h in headers if h['name'].lower() == 'message-id'), None)

            email_details.append({
                "id": msg['id'], "threadId": msg['threadId'], "message_id_header": message_id_header,
                "subject": subject, "snippet": msg.get('snippet', ''), "sender_email": sender_email
            })
        return email_details
    except HttpError as error:
        print(f"Erreur API (vérification emails) : {error}")
        return []

def mark_email_as_read(service, msg_id):
    try:
        service.users().messages().modify(userId='me', id=msg_id, body={'removeLabelIds': ['UNREAD']}).execute()
        print(f"  -> Message {msg_id} marqué comme lu.")
        return True
    except HttpError as error:
        print(f"  -> Impossible de marquer l'email {msg_id} comme lu : {error}")
        return False

def send_reply(service, original_email, reply_body):
    """Construit et envoie une réponse en utilisant le service Gmail authentifié."""
    try:
        original_subject = original_email['subject'].replace("Re: ", "").replace("Fwd: ", "")
        
        message = EmailMessage()
        message.set_content(reply_body)
        message['To'] = original_email['sender_email']
        message['From'] = 'me' # L'API remplace 'me' par l'adresse du compte authentifié
        message['Subject'] = f"Re: {original_subject}"
        message['In-Reply-To'] = original_email['message_id_header']
        message['References'] = original_email['message_id_header']

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        create_message = {
            'raw': encoded_message,
            'threadId': original_email['threadId']
        }
        
        sent_message = service.users().messages().send(userId='me', body=create_message).execute()
        print(f"  -> Réponse envoyée avec succès. Message ID: {sent_message['id']}")
        return True

    except HttpError as error:
        print(f"  -> Erreur lors de l'envoi de la réponse : {error}")
        return False

async def get_eva_reply_text(email):
    """Interroge EVA pour obtenir uniquement le corps du texte de la réponse."""
    prompt = (
        f"Tâche : Rédige une réponse professionnelle et concise à l'email suivant.\n"
        f"Expéditeur : {email['sender_email']}\n"
        f"Extrait : \"{email['snippet']}\"\n\n"
        "Ne génère que le texte brut de la réponse, sans aucune phrase d'introduction ou de conclusion du type 'Voici la réponse'."
    )
    print(f"\n--- Interrogation d'EVA pour répondre à : \"{email['subject']}\" ---")
    try:
        async with websockets.connect(FLASK_WEBSOCKET_URL) as websocket:
            await websocket.send(json.dumps({"text": prompt}))
            while True:
                response_str = await websocket.recv()
                response_json = json.loads(response_str)
                if response_json.get("type") == "final_text":
                    reply_text = response_json.get('text', '').strip()
                    print(f"  -> Texte généré par EVA : \"{reply_text[:80]}...\"")
                    return reply_text
    except Exception as e:
        print(f"Erreur WebSocket : {e}")
        return None

async def main(token_file, silent_mode, reply_all_mode):
    if not silent_mode:
        print("Démarrage de l'agent de réponse automatique pour EVA...")
        print(f"Utilisation du fichier d'authentification : {token_file}")
        if reply_all_mode:
            print("\n[INFO] Mode 'Répondre à tous' ACTIVÉ.")
            print(f"[INFO] {len(EXCLUDED_PREFIXES)} préfixe(s) dans la liste d'exclusion.")
        else:
            print(f"\n[INFO] Mode de surveillance standard ACTIVÉ pour {len(CONTACTS_TO_MONITOR)} contact(s).")
    
    creds = get_google_credentials(token_file)
    if not creds: return
        
    gmail_service = build('gmail', 'v1', credentials=creds)

    while True:
        if not silent_mode:
            print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Lancement de la vérification...")
        
        new_emails = check_for_new_emails(gmail_service, reply_all_mode, silent_mode)
        
        if not new_emails:
            if not silent_mode:
                print("Aucun nouvel email pertinent trouvé.")
        else:
            if silent_mode:
                 print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Nouvel email(s) détecté !")

            for email in new_emails:
                print(f"Traitement de l'email de '{email['sender_email']}' (ID: {email['id']})")
                
                # 1. Obtenir le texte de la réponse d'EVA
                reply_text = await get_eva_reply_text(email)
                
                # 2. Si un texte a été généré, l'envoyer en utilisant le bon compte
                if reply_text:
                    send_reply(gmail_service, email, reply_text)

                # 3. Marquer l'email comme lu
                if mark_email_as_read(gmail_service, email['id']):
                    processed_message_ids.add(email['id'])
        
        await asyncio.sleep(POLLING_INTERVAL_SECONDS)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent de réponse automatique pour EVA.")
    parser.add_argument(
        '--token', type=str, default='token.pickle',
        help="Chemin vers le fichier .pickle d'authentification."
    )
    parser.add_argument(
        '--silencieux', action='store_true',
        help="Exécute le script sans afficher les logs de routine."
    )
    parser.add_argument(
        '--replyall', action='store_true',
        help="Active le mode de réponse à tous les emails non lus (sauf exclusions)."
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(args.token, args.silencieux, args.replyall))
    except KeyboardInterrupt:
        print("\nAgent arrêté par l'utilisateur.")
