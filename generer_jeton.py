import pickle
import os.path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Ce scope accorde un accès complet à la boîte aux lettres.
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify',
        
        
        ]

def create_pickle_file():
    """
    Crée un fichier .pickle pour l'authentification à l'API Gmail
    avec une gestion des erreurs d'entrée.
    """
    pickle_filename = input("Entrez le nom du fichier .pickle à créer (ex: eva.pickle): ")

    # Vérification que l'utilisateur a bien saisi un nom.
    if not pickle_filename.strip():
        print("Erreur : Le nom du fichier ne peut pas être vide. Opération annulée.")
        return

    creds = None
    # Si le fichier pickle existe déjà, on le charge.
    if os.path.exists(pickle_filename):
        with open(pickle_filename, 'rb') as token:
            creds = pickle.load(token)

    # Si les informations d'identification n'existent pas ou ne sont pas valides.
    if not creds or not creds.valid:
        # Si le jeton est expiré et qu'un jeton de rafraîchissement existe, on le rafraîchit.
        if creds and creds.expired and creds.refresh_token:
            print("Rafraîchissement du jeton...")
            creds.refresh(Request())
        else:
            # Sinon, on lance le flux d'authentification pour en obtenir un nouveau.
            print("Lancement de la procédure d'authentification...")
            flow = InstalledAppFlow.from_client_secrets_file(
                'client_secret.json', SCOPES)
            creds = flow.run_local_server(port=0)

        # On enregistre les informations d'identification (nouvelles ou rafraîchies).
        with open(pickle_filename, 'wb') as token:
            pickle.dump(creds, token)
        print(f"Le fichier '{pickle_filename}' a été créé/mis à jour avec succès.")
    else:
        print(f"Le fichier '{pickle_filename}' est déjà valide.")

if __name__ == '__main__':
    create_pickle_file()