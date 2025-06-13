# spotify_controller.py
import os
import sys
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
import time

# Charger les variables d'environnement du fichier .env
load_dotenv()

# --- Configuration ---
# Assurez-vous que votre fichier .env contient vos identifiants.
#
# !!! INSTRUCTION CRITIQUE POUR L'ERREUR "INVALID REDIRECT URI" !!!
# Vous DEVEZ aller sur votre tableau de bord Spotify Developer : https://developer.spotify.com/dashboard
# Allez dans les paramètres de votre application et ajoutez l'URI suivante dans "Redirect URIs":
# http://localhost:8888/callback
# L'URI doit correspondre EXACTEMENT à la valeur de SPOTIPY_REDIRECT_URI dans votre fichier .env.

# Définition des permissions (scopes) nécessaires pour contrôler la lecture
SCOPE = "user-read-playback-state,user-modify-playback-state"

def get_spotify_client():
    """
    Initialise et retourne un client Spotipy authentifié.
    Gère le flux d'authentification OAuth2 et la mise en cache des tokens.
    """
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=SCOPE, cache_path=".spotify_cache"))
        # Vérifier si l'authentification a réussi en tentant une action simple
        sp.current_user()
        return sp
    except Exception as e:
        print(f"Erreur lors de l'authentification Spotify: {e}")
        print("Veuillez vérifier vos identifiants dans le fichier .env et que l'URI de redirection est correctement configurée sur le tableau de bord Spotify Developer.")
        sys.exit(1)

def ensure_active_device(sp):
    """
    Vérifie si un appareil est actif. Si non, tente d'activer le premier appareil disponible.
    Retourne True si un appareil est actif ou a été activé, False sinon.
    """
    try:
        devices_info = sp.devices()
        devices = devices_info.get('devices', [])

        if not devices:
            print("Erreur: Aucun appareil Spotify (actif ou inactif) n'a été trouvé.")
            print("Veuillez lancer Spotify sur l'un de vos appareils (PC, téléphone, etc.).")
            return False

        # Vérifier s'il y a déjà un appareil actif
        active_device = next((d for d in devices if d.get('is_active')), None)
        if active_device:
            return True

        # Si aucun appareil n'est actif, essayer de transférer la lecture au premier appareil de la liste
        first_available_device_id = devices[0].get('id')
        if first_available_device_id:
            print(f"Aucun appareil actif. Tentative de transfert vers l'appareil : {devices[0].get('name')}")
            sp.transfer_playback(device_id=first_available_device_id, force_play=False)
            # Laisser un court instant pour que le transfert soit effectif
            time.sleep(1)
            return True
        
        return False # Ne devrait pas arriver si la première condition a trouvé des appareils
    except Exception as e:
        print(f"Erreur lors de la vérification/activation de l'appareil : {e}")
        return False

def play(sp, query=None):
    """
    Joue une musique ou une playlist sur Spotify.
    Si aucun 'query' n'est fourni, reprend la lecture en cours.
    """
    if not ensure_active_device(sp):
        return

    # Si une requête de recherche est fournie, on cherche et on lance la musique
    if query:
        try:
            results = sp.search(q=query, limit=1, type='track')
            tracks = results['tracks']['items']

            if not tracks:
                print(f"Aucune piste trouvée pour '{query}'.")
                return

            track_uri = tracks[0]['uri']
            track_name = tracks[0]['name']
            artist_name = tracks[0]['artists'][0]['name']
            
            print(f"Lancement de '{track_name}' par {artist_name}...")
            sp.start_playback(uris=[track_uri])

        except Exception as e:
            print(f"Une erreur est survenue lors de la recherche et lecture : {e}")
    # Si aucune requête n'est fournie, on reprend simplement la lecture
    else:
        try:
            print("Reprise de la lecture...")
            sp.start_playback()
        except Exception as e:
            print(f"Une erreur est survenue lors de la reprise de la lecture : {e}")

def resume_playback(sp):
    """Reprend la lecture de la musique actuelle."""
    play(sp) # La fonction play sans argument gère maintenant la reprise

def pause(sp):
    """Met la lecture en pause."""
    if not ensure_active_device(sp):
        return
    try:
        print("Mise en pause de la musique.")
        sp.pause_playback()
    except Exception as e:
        print(f"Erreur lors de la mise en pause : {e}")

def next_track(sp):
    """Passe à la musique suivante."""
    if not ensure_active_device(sp):
        return
    try:
        print("Passage à la musique suivante.")
        sp.next_track()
    except Exception as e:
        print(f"Erreur lors du passage à la musique suivante : {e}")

def previous_track(sp):
    """Passe à la musique précédente."""
    if not ensure_active_device(sp):
        return
    try:
        print("Passage à la musique précédente.")
        sp.previous_track()
    except Exception as e:
        print(f"Erreur lors du passage à la musique précédente : {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python spotify_controller.py play <nom de la musique>  (pour chercher et jouer)")
        print("  python spotify_controller.py play                     (pour reprendre la lecture)")
        print("  python spotify_controller.py resume                   (alias pour reprendre)")
        print("  python spotify_controller.py pause")
        print("  python spotify_controller.py next")
        print("  python spotify_controller.py previous")
        sys.exit(1)

    command = sys.argv[1].lower()
    spotify_client = get_spotify_client()

    if command == "play":
        # La requête est tout ce qui suit la commande "play", si présent
        search_query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else None
        play(spotify_client, search_query)
    elif command == "resume":
        resume_playback(spotify_client)
    elif command == "pause":
        pause(spotify_client)
    elif command == "next":
        next_track(spotify_client)
    elif command == "previous":
        previous_track(spotify_client)
    else:
        print(f"Commande non reconnue: '{command}'")