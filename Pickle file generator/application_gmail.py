import pickle
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Nom du fichier pickle contenant les informations d'identification.
PICKLE_FILE = 'eva.pickle'
# Scopes requis par l'application. Doivent correspondre à ceux du jeton.
SCOPES = ['https://mail.google.com/']

def get_gmail_service():
    """
    Charge les informations d'identification et retourne un objet service pour l'API Gmail.
    """
    creds = None
    if os.path.exists(PICKLE_FILE):
        with open(PICKLE_FILE, 'rb') as token:
            creds = pickle.load(token)

    # Si les informations d'identification ne sont pas valides, les rafraîchir ou arrêter.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Sauvegarder les nouvelles informations pour les prochaines exécutions.
            with open(PICKLE_FILE, 'wb') as token:
                pickle.dump(creds, token)
        else:
            print(f"Erreur: Fichier '{PICKLE_FILE}' non trouvé ou invalide.")
            print("Veuillez d'abord exécuter le script de génération de jeton.")
            return None # Retourne None si l'authentification échoue.

    try:
        service = build('gmail', 'v1', credentials=creds)
        return service
    except HttpError as error:
        print(f"Une erreur est survenue lors de la création du service: {error}")
        return None

# --- DÉBUT DE LA LOGIQUE DE VOTRE APPLICATION ---
if __name__ == '__main__':
    gmail_service = get_gmail_service()

    if gmail_service:
        print("Authentification réussie. Le service Gmail est prêt.")
        #
        # C'EST ICI QUE VOUS METTEZ VOTRE CODE POUR LIRE OU ENVOYER DES EMAILS
        # Exemple : lister les labels de la boîte de réception
        #
        try:
            results = gmail_service.users().labels().list(userId='me').execute()
            labels = results.get('labels', [])
            if not labels:
                print('Aucun label trouvé.')
            else:
                print('Labels:')
                for label in labels:
                    print(f"- {label['name']}")
        except HttpError as error:
            print(f"Une erreur est survenue: {error}")