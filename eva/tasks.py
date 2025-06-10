import os
import traceback
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .auth import get_google_credentials
from .config import TOKEN_PICKLE_FILE


def create_google_task(title, notes=None):
    creds = get_google_credentials()
    if not creds:
        return "Authentification Google requise pour créer des tâches. Veuillez autoriser via /authorize_google."
    if not title or not title.strip():
        return "Le titre de la tâche ne peut pas être vide."
    try:
        service = build('tasks', 'v1', credentials=creds)
        tasklists_response = service.tasklists().list(maxResults=10).execute()
        tasklists = tasklists_response.get('items', [])
        tasklist_id = None
        tasklist_title = "par défaut"
        if not tasklists:
            try:
                created_list = service.tasklists().insert(body={'title': 'Ma Liste'}).execute()
                tasklist_id = created_list['id']
                tasklist_title = created_list['title']
            except HttpError as list_error:
                print(f"Erreur lors de la création de la liste de tâches par défaut: {list_error}")
                return "Aucune liste de tâches trouvée et la création automatique a échoué."
        else:
            preferred_list_titles = ["ma liste", "my tasks", "tâches", "tasks"]
            for tl in tasklists:
                if tl.get('title', '').lower() in preferred_list_titles:
                    tasklist_id = tl['id']
                    tasklist_title = tl['title']
                    break
            if not tasklist_id:
                tasklist_id = tasklists[0]['id']
                tasklist_title = tasklists[0].get('title', 'inconnue')

        task_body = {'title': title}
        if notes and notes.strip():
            task_body['notes'] = notes
        created_task = service.tasks().insert(tasklist=tasklist_id, body=task_body).execute()
        return f"Tâche '{created_task['title']}' ajoutée à la liste '{tasklist_title}'."
    except HttpError as error:
        error_content = error.content.decode('utf-8') if error.content else "Aucun détail."
        print(f"Erreur API Tasks (création): {error.resp.status} - {error.resp.reason} - {error_content}")
        if error.resp.status == 401 or 'invalid_grant' in str(error).lower():
            if os.path.exists(TOKEN_PICKLE_FILE):
                os.remove(TOKEN_PICKLE_FILE)
            return "Identifiants Tasks invalides/révoqués. Réauthentifiez-vous."
        return f"Erreur lors de la création de la tâche ({error.resp.status}): {error_content}."
    except Exception as e:
        print(f"Erreur inattendue lors de la création de la tâche (Tasks): {e}")
        traceback.print_exc()
        return f"Erreur inattendue lors de la création de la tâche: {type(e).__name__}"


def list_google_tasks(max_results=10):
    creds = get_google_credentials()
    if not creds:
        return "Authentification Google requise pour Tasks. Veuillez autoriser via /authorize_google."
    try:
        service = build('tasks', 'v1', credentials=creds)
        all_tasklists_response = service.tasklists().list(maxResults=20).execute()
        all_tasklists = all_tasklists_response.get('items', [])
        if not all_tasklists:
            return "Aucune liste de tâches trouvée."
        tasklist_id = all_tasklists[0]['id']
        tasklist_title = all_tasklists[0].get('title', 'par défaut')
        preferred_list_titles = ["ma liste", "my tasks", "tâches", "tasks"]
        for tl in all_tasklists:
            if tl.get('title', '').lower() in preferred_list_titles:
                tasklist_id = tl['id']
                tasklist_title = tl['title']
                break

        results = service.tasks().list(tasklist=tasklist_id, maxResults=int(max_results), showCompleted=False, showHidden=False).execute()
        tasks = results.get('items', [])
        if not tasks:
            return f"Aucune tâche active trouvée dans la liste '{tasklist_title}'."
        task_list_details = f"Voici vos tâches actives de la liste '{tasklist_title}' :\n"
        for task in tasks:
            task_list_details += f"- {task.get('title', 'Tâche sans titre')}\n"
            if task.get('notes'):
                task_list_details += f"  Notes: {task.get('notes')}\n"
        return task_list_details
    except HttpError as error:
        error_content = error.content.decode('utf-8') if error.content else "Aucun détail."
        print(f"Erreur API Tasks (lecture): {error.resp.status} - {error.resp.reason} - {error_content}")
        if error.resp.status == 401 or 'invalid_grant' in str(error).lower():
            if os.path.exists(TOKEN_PICKLE_FILE):
                os.remove(TOKEN_PICKLE_FILE)
            return "Identifiants Tasks invalides/révoqués. Réauthentifiez-vous."
        return f"Erreur lors de l'accès à Tasks ({error.resp.status}): {error_content}"
    except Exception as e:
        print(f"Erreur inattendue lors de l'accès à Tasks (lecture): {e}")
        traceback.print_exc()
        return f"Erreur inattendue lors de l'accès à Tasks: {type(e).__name__}"


def find_task_id(service, task_title):
    try:
        tasklists = service.tasklists().list().execute().get('items', [])
        if not tasklists:
            return None, None
        for tasklist in tasklists:
            tasks = service.tasks().list(tasklist=tasklist['id'], showCompleted=False).execute().get('items', [])
            for task in tasks:
                if task.get('title', '').lower() == task_title.lower():
                    return task['id'], tasklist['id']
        return None, None
    except Exception as e:
        print(f"Erreur lors de la recherche de l'ID de la tâche : {e}")
        return None, None


def delete_google_task(title):
    creds = get_google_credentials()
    if not creds:
        return "Authentification Google requise."
    try:
        service = build('tasks', 'v1', credentials=creds)
        task_id, tasklist_id = find_task_id(service, title)
        if not task_id:
            return f"Tâche '{title}' non trouvée dans les listes actives."
        service.tasks().delete(tasklist=tasklist_id, task=task_id).execute()
        return f"Tâche '{title}' supprimée."
    except Exception as e:
        traceback.print_exc()
        return f"Erreur lors de la suppression de la tâche : {e}"


def update_google_task(old_title, new_title):
    creds = get_google_credentials()
    if not creds:
        return "Authentification Google requise."
    try:
        service = build('tasks', 'v1', credentials=creds)
        task_id, tasklist_id = find_task_id(service, old_title)
        if not task_id:
            return f"Tâche '{old_title}' non trouvée."
        task_body = {'id': task_id, 'title': new_title}
        updated_task = service.tasks().patch(tasklist=tasklist_id, task=task_id, body=task_body).execute()
        return f"Tâche renommée en '{updated_task['title']}'."
    except Exception as e:
        traceback.print_exc()
        return f"Erreur lors de la mise à jour de la tâche : {e}"
