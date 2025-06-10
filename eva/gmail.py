import os
import base64
import traceback
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .auth import get_google_credentials
from .config import TOKEN_PICKLE_FILE


def list_unread_emails(max_results=10):
    creds = get_google_credentials()
    if not creds:
        return "Authentification Google requise pour Gmail. Veuillez autoriser via /authorize_google."
    try:
        service = build('gmail', 'v1', credentials=creds)
        results = service.users().messages().list(userId='me', labelIds=['INBOX', 'UNREAD'], maxResults=int(max_results)).execute()
        messages = results.get('messages', [])
        if not messages:
            return "Aucun e-mail non lu trouvé."
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
            if os.path.exists(TOKEN_PICKLE_FILE):
                os.remove(TOKEN_PICKLE_FILE)
            return "Identifiants Gmail invalides/révoqués. Réauthentifiez-vous."
        return f"Erreur lors de l'accès à Gmail: {error.resp.status} - {error._get_reason()}"
    except Exception as e:
        print(f"Erreur inattendue lors de l'accès à Gmail (lecture): {e}")
        traceback.print_exc()
        return f"Erreur inattendue lors de l'accès à Gmail: {type(e).__name__}"


def send_email(to_address: str, subject: str, message_text: str):
    creds = get_google_credentials()
    if not creds:
        return "Authentification Google requise pour envoyer des e-mails. Veuillez autoriser via /authorize_google."
    try:
        service = build('gmail', 'v1', credentials=creds)
        mime_message = MIMEText(message_text, 'plain', 'utf-8')
        mime_message['to'] = to_address
        mime_message['subject'] = subject
        encoded_message = base64.urlsafe_b64encode(mime_message.as_bytes()).decode()
        create_message_body = {'raw': encoded_message}
        service.users().messages().send(userId='me', body=create_message_body).execute()
        return f"E-mail envoyé avec succès à {to_address} avec l'objet '{subject}'."
    except HttpError as error:
        error_content = error.content.decode('utf-8') if error.content else "Aucun détail."
        print(f"Erreur API Gmail (envoi): {error.resp.status} - {error.resp.reason} - {error_content}")
        if error.resp.status == 401 or 'invalid_grant' in str(error).lower():
            if os.path.exists(TOKEN_PICKLE_FILE):
                os.remove(TOKEN_PICKLE_FILE)
            return "Identifiants Gmail invalides/révoqués. Réauthentifiez-vous."
        elif error.resp.status == 400:
            return f"Erreur lors de la préparation de l'e-mail (400): {error_content}. Vérifiez l'adresse du destinataire."
        return f"Erreur lors de l'envoi de l'e-mail ({error.resp.status}): {error_content}"
    except Exception as e:
        print(f"Erreur inattendue lors de l'envoi de l'e-mail (Gmail): {e}")
        traceback.print_exc()
        return f"Erreur inattendue lors de l'envoi de l'e-mail: {type(e).__name__}"
