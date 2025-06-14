# multi_step_agent.py
import os
import sys
import json
import traceback
import re
import requests # Pour les appels à l'API de recherche Google
import io
import contextlib
import subprocess # Ajouté pour lancer des processus externes

import google.generativeai as genai
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()
# Assurez-vous que la clé API pour ce modèle est bien définie
gemini_api_key = os.getenv("GEMINI_API_KEY") 
if not gemini_api_key:
    print(json.dumps({"type": "error", "content": "Clé API Gemini manquante pour l'agent."}), flush=True)
    sys.exit(1)

# --- Configuration pour Google Custom Search ---
google_custom_search_api_key = os.getenv("GOOGLE_CUSTOM_SEARCH_API_KEY")
google_custom_search_cx = os.getenv("GOOGLE_CUSTOM_SEARCH_CX")
google_search_enabled = bool(google_custom_search_api_key and google_custom_search_cx)


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

        # Valider que l'entrée est bien un JSON
        try:
            json.loads(sequence_json)
        except json.JSONDecodeError:
            return "Erreur : le paramètre 'sequence_json' n'est pas une chaîne JSON valide."

        # Lance le script contrôleur dans un autre processus
        command = [sys.executable, controller_path, sequence_json]
        subprocess.Popen(command)

        return f"La séquence musicale a été envoyée à FL Studio."
    except Exception as e:
        return f"Erreur lors du lancement de la séquence musicale : {e}"


AVAILABLE_TOOLS = {
    "web_search": {
        "function": web_search,
        "description": "Recherche sur le web pour obtenir des informations actuelles ou générales. Utiliser pour des questions sur des lieux, des personnes, des événements, etc.",
        "params": {"query": "string", "num_results": "integer (optionnel, défaut 5)"}
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
À chaque étape, tu dois :
1.  **Thought**: Réfléchir à la tâche, analyser les informations disponibles, et planifier ta prochaine action. Explique ton raisonnement.
2.  **Action**: Choisir UN outil parmi ceux disponibles et fournir les paramètres nécessaires.
Tu dois formater ta réponse exclusivement en JSON avec les clés "thought" et "action".
L'objet "action" doit contenir "tool_name" et "parameters".

Outils disponibles :
{json.dumps({name: {"description": tool["description"], "params": tool["params"]} for name, tool in AVAILABLE_TOOLS.items()}, indent=2)}

Lorsque tu as terminé et que tu as la réponse finale, utilise l'outil spécial "finish" avec le paramètre "answer" contenant la solution complète.
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
            print(json.dumps({"type": "error", "content": error_message}), flush=True)
            break

        print(json.dumps({"type": "thought", "content": thought}), flush=True)
        history.append(f"Thought: {thought}")

        if not tool_name:
            print(json.dumps({"type": "error", "content": "L'agent n'a pas choisi d'outil."}), flush=True)
            break

        print(json.dumps({"type": "action", "tool": tool_name, "params": parameters}), flush=True)
        history.append(f"Action: {tool_name} avec params {parameters}")

        if tool_name == "finish":
            final_answer = parameters.get("answer", "Tâche terminée sans réponse finale explicite.")
            print(json.dumps({"type": "final_answer", "content": final_answer}), flush=True)
            break

        if tool_name in AVAILABLE_TOOLS:
            output_capture = io.StringIO()
            error_capture = io.StringIO()
            try:
                tool_function = AVAILABLE_TOOLS[tool_name]["function"]
                # Redirige stdout/stderr pour capturer toute sortie parasite des bibliothèques
                with contextlib.redirect_stdout(output_capture), contextlib.redirect_stderr(error_capture):
                    tool_result = tool_function(**parameters)

                # Combine le résultat de la fonction et les sorties capturées
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

        print(json.dumps({"type": "observation", "content": str(observation)}), flush=True)
        history.append(f"Observation: {observation}")

    else:
        print(json.dumps({"type": "error", "content": "L'agent a atteint le nombre maximum d'étapes sans terminer la tâche."}), flush=True)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
        run_agent_loop(task)
    else:
        print(json.dumps({"type": "error", "content": "Aucune tâche fournie à l'agent."}), flush=True)
