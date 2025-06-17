# multi_step_agent.py
import os
import sys
import json
import traceback
import re
import requests  # Pour les appels HTTP (recherche et contenu de page)
from bs4 import BeautifulSoup # Pour parser le HTML
import io
import contextlib
import subprocess
import googlemaps # Ajouté pour le géocodage
import urllib.parse
# Nouveaux imports pour l'analyse d'images
from PIL import Image

import google.generativeai as genai
from dotenv import load_dotenv

# Force la sortie standard en UTF-8 pour éviter les erreurs de décodage Unicode sous Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- Configuration ---
load_dotenv()
# Assurez-vous que la clé API pour ce modèle est bien définie
gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    print(json.dumps({"type": "error", "content": "Clé API Gemini manquante pour l'agent."}), flush=True)
    sys.exit(1)

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
    Récupère et extrait le contenu textuel d'une page web à partir de son URL.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

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

def analyze_image(url: str, question: str = "Décris cette image en détail. Si c'est une personne, essaie de l'identifier si c'est une célébrité.") -> str:
    """
    Analyse une image à partir d'une URL. Télécharge l'image, puis utilise un modèle
    multimodal pour répondre à une question à son sujet ou pour la décrire.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, timeout=15)
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

# NOUVELLE FONCTION
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
        
        # L'URL construite avec les paramètres est l'URL de l'image elle-même.
        image_url = f"{base_url}?{urllib.parse.urlencode(params)}"
        
        # Retourne un objet JSON structuré que le frontend peut interpréter
        return json.dumps({
            "type": "image",
            "url": image_url,
            "caption": f"Aperçu Street View pour les coordonnées ({latitude:.4f}, {longitude:.4f})"
        })
        
    except Exception as e:
        return json.dumps({"type": "error", "content": f"Erreur API Street View: {e}"})    


AVAILABLE_TOOLS = {
    "web_search": {
        "function": web_search,
        "description": "Recherche sur le web pour obtenir des informations générales ou des URL. Utiliser pour des questions sur des lieux, des personnes, des événements, etc.",
        "params": {"query": "string", "num_results": "integer (optionnel, défaut 5)"}
    },
    "view_webpage": {
        "function": view_webpage,
        "description": "Extrait le contenu textuel d'une page web à partir de son URL. À utiliser après une recherche web pour analyser le contenu d'une page spécifique.",
        "params": {"url": "string (URL complète de la page à lire)"}
    },
    # NOUVEL OUTIL AJOUTÉ
    "locate_on_map": {
        "function": locate_on_map,
        "description": "Trouve et affiche un lieu sur une carte. Utilise cet outil lorsque l'utilisateur demande de montrer, localiser ou afficher un endroit.",
        "params": {"location_name": "string (Le nom de la ville, du monument, ou de l'adresse à localiser)"}
    },
    # NOUVEL OUTIL POUR STREET VIEW
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
    }
}


AGENT_SYSTEM_PROMPT = f"""
Tu es un agent autonome intelligent. Ta mission est de résoudre la tâche donnée en utilisant une chaîne de pensée (Thought) et d'action (Action).

# INSTRUCTIONS DE BASE
1.  **Thought**: À chaque étape, réfléchis à la tâche, analyse les informations disponibles, et planifie ta prochaine action. Explique ton raisonnement de manière concise.
2.  **Action**: Choisis UN seul outil parmi ceux disponibles et fournis les paramètres nécessaires.
3.  **Format**: Ta réponse doit être exclusivement en JSON avec les clés "thought" et "action". L'objet "action" doit contenir "tool_name" et "parameters".

# STRATÉGIE ET RAISONNEMENT
- **Décomposition Logique**: Décompose les problèmes complexes en une séquence d'étapes logiques où la sortie d'une action devient l'entrée de la suivante. Ne saute pas d'étapes.
- **Utilisation des Données Initiales**: Si la tâche initiale que l'on te donne contient des données spécifiques (comme une URL), tu DOIS les utiliser comme paramètres pour tes premières actions. N'invente pas de nouvelles données si elles sont déjà fournies.
- **Vérification Critique**: Ne te contente pas de la première réponse plausible. Après avoir identifié un lieu potentiel, effectue une étape de VÉRIFICATION. Utilise `web_search` une seconde fois avec une requête comme "photo de [nom du lieu trouvé]" pour trouver des images de ce lieu. Compare mentalement les détails de ces nouvelles images avec la description de l'image originale. Si les détails ne correspondent pas, revois tes hypothèses et cherche d'autres pistes.
- **Exemple de tâche complexe : "Où cette photo a-t-elle été prise ?"**
    1.  **Analyse d'abord l'image** avec `analyze_image` pour extraire des indices uniques.
    2.  **Utilise ces indices** avec `web_search` pour trouver un nom de lieu probable.
    3.  **Vérifie** ce lieu en cherchant d'autres images avec `web_search`.
    4.  Si la vérification est concluante, **convertis le nom en coordonnées** avec `locate_on_map`.
    5.  **Utilise `get_street_view_image`** pour la visualisation finale.
- **Réponse Finale**: Lorsque tu as la réponse complète et VÉRIFIÉE, utilise l'outil spécial "finish".

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

        if tool_name == "finish":
            final_answer = parameters.get("answer", "Tâche terminée sans réponse finale explicite.")
            print(json.dumps({"type": "final_answer", "content": final_answer}, ensure_ascii=False), flush=True)
            break

        if tool_name in AVAILABLE_TOOLS:
            output_capture = io.StringIO()
            error_capture = io.StringIO()
            try:
                tool_function = AVAILABLE_TOOLS[tool_name]["function"]
                # Redirige stdout/stderr pour capturer toute sortie parasite des bibliothèques
                with contextlib.redirect_stdout(output_capture), contextlib.redirect_stderr(error_capture):
                    tool_result = tool_function(**parameters)

                stdout_val = output_capture.getvalue()
                stderr_val = error_capture.getvalue()
                
                observation = str(tool_result)
                if stdout_val:
                    observation += f"\n\n[Sortie standard capturée]:\n{stdout_val}"
                if stderr_val:
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
