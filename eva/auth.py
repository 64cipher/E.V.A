import os
import pickle
import traceback

from flask import jsonify, redirect, session, url_for, request
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

from .config import CLIENT_SECRETS_FILE, SCOPES, TOKEN_PICKLE_FILE


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
        with open(TOKEN_PICKLE_FILE, 'wb') as token_file:
            pickle.dump(creds, token_file)
    return creds


def authorize_google():
    if not os.path.exists(CLIENT_SECRETS_FILE):
        return jsonify({"error": f"Fichier {CLIENT_SECRETS_FILE} non trouvé."}), 500
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for('oauth2callback_google', _external=True),
    )
    authorization_url, state = flow.authorization_url(access_type='offline', prompt='consent')
    session['oauth_state'] = state
    return redirect(authorization_url)


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
        redirect_uri=url_for('oauth2callback_google', _external=True),
    )
    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception as e:
        print(f"ERREUR détaillée lors de fetch_token: {traceback.format_exc()}")
        return jsonify({"error": f"Échec de la récupération des tokens OAuth: {e}."}), 500

    credentials = flow.credentials
    with open(TOKEN_PICKLE_FILE, 'wb') as token_file:
        pickle.dump(credentials, token_file)

    return (
        "<html><head><title>Authentification Réussie</title></head>"
        "<body><h1>Authentification Google Réussie!</h1><p>Vous pouvez fermer cette fenêtre.</p>"
        "<script>setTimeout(function() { window.close(); }, 1000);</script></body></html>"
    )
