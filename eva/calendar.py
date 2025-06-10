import os
import datetime
import traceback
import time
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .auth import get_google_credentials
from .config import TOKEN_PICKLE_FILE
from .utils import parse_french_datetime


def create_calendar_event(summary, start_datetime_obj, duration_hours=1):
    creds = get_google_credentials()
    if not creds:
        return "Authentification Google requise pour ajouter des événements au calendrier. Veuillez autoriser via /authorize_google."
    if not summary or not summary.strip():
        return "Le titre de l'événement ne peut pas être vide."
    if not isinstance(start_datetime_obj, datetime.datetime):
        return "Date et heure de début invalides pour l'événement."
    end_datetime_obj = start_datetime_obj + datetime.timedelta(hours=duration_hours)
    event_body = {
        'summary': summary,
        'start': {'dateTime': start_datetime_obj.isoformat(), 'timeZone': 'Europe/Paris'},
        'end': {'dateTime': end_datetime_obj.isoformat(), 'timeZone': 'Europe/Paris'},
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'popup', 'minutes': 30},
                {'method': 'popup', 'minutes': 10}
            ],
        },
    }
    try:
        service = build('calendar', 'v3', credentials=creds)
        created_event = service.events().insert(calendarId='primary', body=event_body).execute()
        event_link = created_event.get('htmlLink', 'Lien non disponible')
        return f"Événement '{summary}' ajouté à votre calendrier pour le {start_datetime_obj.strftime('%d %B %Y à %Hh%M')}. Lien: {event_link}"
    except HttpError as error:
        error_content = error.content.decode('utf-8') if error.content else "Aucun détail d'erreur."
        print(f"Erreur API Calendar (création événement): Status={error.resp.status}, Raison={error.resp.reason}, Détails={error_content}")
        if error.resp.status == 401 or 'invalid_grant' in str(error).lower():
            if os.path.exists(TOKEN_PICKLE_FILE):
                os.remove(TOKEN_PICKLE_FILE)
            return "Identifiants Calendar invalides/révoqués. Réauthentifiez-vous."
        return f"Erreur lors de la création de l'événement ({error.resp.status}): {error_content}"
    except Exception as e:
        print(f"Erreur inattendue Calendar (création événement): {e}")
        traceback.print_exc()
        return f"Erreur inattendue lors de la création de l'événement: {type(e).__name__}"


def format_event_datetime(start_str: str):
    try:
        now_paris = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=1)))
        is_dst = time.localtime().tm_isdst > 0
        paris_offset_hours = 2 if is_dst else 1
        paris_tz = datetime.timezone(datetime.timedelta(hours=paris_offset_hours))
        if 'T' in start_str:
            if 'Z' in start_str:
                dt_object_utc = datetime.datetime.fromisoformat(start_str.replace('Z', '+00:00'))
            elif '+' in start_str[10:] or '-' in start_str[10:]:
                dt_object_utc = datetime.datetime.fromisoformat(start_str)
            else:
                dt_object_utc = datetime.datetime.fromisoformat(start_str).replace(tzinfo=datetime.timezone.utc)
            dt_object_paris = dt_object_utc.astimezone(paris_tz)
            return dt_object_paris.strftime("%d %B %Y à %Hh%M")
        else:
            dt_object_date = datetime.datetime.strptime(start_str, "%Y-%m-%d")
            return dt_object_date.strftime("%d %B %Y")
    except ValueError as e:
        print(f"Error formatting event datetime '{start_str}': {e}")
        return start_str


def find_event_id(service, summary_hint, start_dt_obj, original_datetime_str):
    summary_hint_lower = summary_hint.lower()
    is_date_only_query = 'h' not in original_datetime_str.lower()
    if is_date_only_query:
        time_min = start_dt_obj.replace(hour=0, minute=0, second=0).astimezone(datetime.timezone.utc).isoformat()
        time_max = start_dt_obj.replace(hour=23, minute=59, second=59).astimezone(datetime.timezone.utc).isoformat()
    else:
        time_min = (start_dt_obj - datetime.timedelta(minutes=30)).astimezone(datetime.timezone.utc).isoformat()
        time_max = (start_dt_obj + datetime.timedelta(minutes=30)).astimezone(datetime.timezone.utc).isoformat()
    try:
        events_result = service.events().list(calendarId='primary', timeMin=time_min, timeMax=time_max, singleEvents=True, orderBy='startTime').execute()
        events = events_result.get('items', [])
        matching_events = [event for event in events if summary_hint_lower in event.get('summary', '').lower()]
        if len(matching_events) == 0:
            return 'not_found', None
        elif len(matching_events) == 1:
            return 'success', matching_events[0]['id']
        else:
            return 'multiple_found', matching_events
    except Exception as e:
        print(f"Erreur lors de la recherche de l'ID de l'événement : {e}")
        traceback.print_exc()
        return 'error', str(e)


def delete_calendar_event(summary: str, datetime_str: str):
    creds = get_google_credentials()
    if not creds:
        return "Authentification Google requise."
    start_dt_obj = parse_french_datetime(datetime_str)
    if not start_dt_obj:
        return f"Date '{datetime_str}' non comprise."
    try:
        service = build('calendar', 'v3', credentials=creds)
        status, data = find_event_id(service, summary, start_dt_obj, datetime_str)
        if status == 'not_found':
            return f"Événement '{summary}' non trouvé pour le {start_dt_obj.strftime('%d %B %Y')}."
        if status == 'error':
            return f"Une erreur est survenue lors de la recherche de l'événement : {data}"
        if status == 'multiple_found':
            response_text = f"J'ai trouvé plusieurs événements correspondant à '{summary}'. Lequel souhaitez-vous supprimer ?\n"
            for event in data:
                start_formatted = format_event_datetime(event['start'].get('dateTime', event['start'].get('date')))
                response_text += f"- '{event['summary']}' le {start_formatted}\n"
            response_text += "Veuillez être plus précis en indiquant l'heure."
            return response_text
        if status == 'success':
            event_id = data
            service.events().delete(calendarId='primary', eventId=event_id).execute()
            return f"Événement '{summary}' supprimé avec succès."
    except Exception as e:
        traceback.print_exc()
        return f"Erreur lors de la suppression de l'événement : {e}"


def update_calendar_event(old_summary: str, old_datetime_str: str, new_summary: str, new_datetime_str: str):
    creds = get_google_credentials()
    if not creds:
        return "Authentification Google requise."
    old_start_dt = parse_french_datetime(old_datetime_str)
    if not old_start_dt:
        return f"Ancienne date '{old_datetime_str}' non comprise."
    if not new_summary and not new_datetime_str:
        return "Veuillez spécifier un nouveau titre ou une nouvelle date/heure pour la modification."
    try:
        service = build('calendar', 'v3', credentials=creds)
        status, data = find_event_id(service, old_summary, old_start_dt, old_datetime_str)
        if status == 'not_found':
            return f"Événement '{old_summary}' non trouvé pour le {old_start_dt.strftime('%d %B %Y')}."
        if status == 'error':
            return f"Une erreur est survenue lors de la recherche de l'événement : {data}"
        if status == 'multiple_found':
            return f"J'ai trouvé plusieurs événements correspondants à '{old_summary}'. Veuillez être plus précis pour la modification."
        if status == 'success':
            event_id = data
            event = service.events().get(calendarId='primary', eventId=event_id).execute()
            if new_summary:
                event['summary'] = new_summary
            if new_datetime_str:
                new_start_dt = parse_french_datetime(new_datetime_str)
                if not new_start_dt:
                    return f"Nouvelle date '{new_datetime_str}' non comprise."
                end_time_old = datetime.datetime.fromisoformat(event['end']['dateTime'])
                start_time_old = datetime.datetime.fromisoformat(event['start']['dateTime'])
                duration = end_time_old - start_time_old
                event['start']['dateTime'] = new_start_dt.isoformat()
                event['end']['dateTime'] = (new_start_dt + duration).isoformat()
            updated_event = service.events().update(calendarId='primary', eventId=event_id, body=event).execute()
            return f"Événement mis à jour : '{updated_event.get('summary', 'Sans titre')}'."
    except Exception as e:
        traceback.print_exc()
        return f"Erreur lors de la mise à jour de l'événement : {e}"
