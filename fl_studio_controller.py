# fl_studio_controller.py (Version 3.0)
import mido
import sys
import time
import json
import re

NOTE_MAP = {
    'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3,
    'E': 4, 'F': 5, 'F#': 6, 'Gb': 6, 'G': 7, 'G#': 8,
    'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11
}

def note_name_to_midi(note_name):
    try:
        match = re.match(r"([A-Ga-g][#b]?)(\d+)", note_name)
        if not match: return None
        note, octave = match.groups()
        return 12 * (int(octave) + 1) + NOTE_MAP[note.capitalize()]
    except Exception:
        return None

def find_midi_port(port_name='loopMIDI Port'):
    available_ports = mido.get_output_names()
    found_port = next((p for p in available_ports if port_name in p), None)
    if not found_port:
        print(f"Erreur: Port MIDI '{port_name}' non trouvé.")
        return None
    return found_port

def _play_single_note(port, event):
    """Joue une seule note. C'est un sous-événement."""
    note_name = event.get('note')
    midi_note = note_name_to_midi(note_name)
    if midi_note is None: return

    velocity = int(event.get('velocity', 100))
    duration = float(event.get('duration', 0.5))

    port.send(mido.Message('note_on', note=midi_note, velocity=velocity))
    print(f"Note On: {note_name}")
    time.sleep(duration)
    port.send(mido.Message('note_off', note=midi_note, velocity=velocity))
    print(f"Note Off: {note_name}")

def _play_chord_from_event(port, event):
    """Joue un accord. C'est un sous-événement."""
    notes_in_chord = event.get('notes', [])
    duration = float(event.get('duration', 1.0))
    midi_notes = []

    for note_info in notes_in_chord:
        note_name = note_info.get('note')
        midi_note = note_name_to_midi(note_name)
        if midi_note is None: continue
        midi_notes.append(midi_note)
        velocity = int(note_info.get('velocity', 100))
        port.send(mido.Message('note_on', note=midi_note, velocity=velocity))
        print(f"Chord Note On: {note_name}")

    if duration > 0:
        time.sleep(duration)

    for midi_note in midi_notes:
        port.send(mido.Message('note_off', note=midi_note))
        print(f"Chord Note Off: {midi_note}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fl_studio_controller.py '<json_sequence_data>'")
        sys.exit(1)

    try:
        # L'argument principal est maintenant une liste d'événements
        sequence = json.loads(sys.argv[1])
        if not isinstance(sequence, list):
            print("Erreur: Le JSON doit être une liste (un tableau) d'événements.")
            sys.exit(1)
    except json.JSONDecodeError:
        print("Erreur: L'argument n'est pas une chaîne JSON valide.")
        sys.exit(1)

    port_path = find_midi_port()
    if not port_path:
        sys.exit(1)

    try:
        with mido.open_output(port_path) as port:
            # Boucle principale qui itère sur chaque événement dans la séquence
            for event in sequence:
                event_type = event.get("type", "").lower()
                if event_type == 'note':
                    _play_single_note(port, event)
                elif event_type == 'chord':
                    _play_chord_from_event(port, event)
                else:
                    print(f"Type d'événement inconnu ignoré: {event_type}")
    except Exception as e:
        print(f"Une erreur MIDI est survenue: {e}")