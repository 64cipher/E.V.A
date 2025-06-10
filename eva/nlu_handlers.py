import datetime
from .tasks import create_google_task
from .contacts import add_contact_to_book


def handle_create_task(entities):
    title = entities.get("title")
    notes = entities.get("notes")
    if title:
        return create_google_task(title, notes)
    return "Quel est le titre de la tâche que vous souhaitez ajouter ?"


def handle_add_contact(entities):
    name = entities.get("name")
    email = entities.get("email")
    if name and email:
        return add_contact_to_book(name, email)
    return "Pour ajouter un contact, veuillez me donner son nom et son adresse e-mail."


def handle_get_weather_forecast(entities):
    return "Prévisions météo pour votre localisation."


def handle_get_current_datetime(entities):
    jours = {
        "Monday": "lundi", "Tuesday": "mardi", "Wednesday": "mercredi",
        "Thursday": "jeudi", "Friday": "vendredi", "Saturday": "samedi", "Sunday": "dimanche"
    }
    mois = {
        "January": "janvier", "February": "février", "March": "mars", "April": "avril",
        "May": "mai", "June": "juin", "July": "juillet", "August": "août",
        "September": "septembre", "October": "octobre", "November": "novembre", "December": "décembre"
    }
    now = datetime.datetime.now()
    jour_fr = jours.get(now.strftime('%A'), now.strftime('%A'))
    mois_fr = mois.get(now.strftime('%B'), now.strftime('%B'))
    return f"Nous sommes le {jour_fr} {now.day} {mois_fr} {now.year} et il est {now.strftime('%Hh%M')}."
