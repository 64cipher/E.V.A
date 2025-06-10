import os
from flask import Flask
from flask_cors import CORS

from eva import config
from eva.auth import authorize_google, oauth2callback_google
from eva.websocket import sock, chat_ws

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": ["http://127.0.0.1:8080", "http://localhost:8080"]}}, supports_credentials=True)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "une_cle_secrete_par_defaut_tres_forte")

sock.init_app(app)
app.add_url_rule('/authorize_google', 'authorize_google', authorize_google)
app.add_url_rule('/oauth2callback_google', 'oauth2callback_google', oauth2callback_google)

sock.route('/api/chat_ws')(chat_ws)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
