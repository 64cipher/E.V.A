# fl_studio_controller.py (Version 5.0 - Lecteur MIDI Robuste)
import mido
import sys
import time
import json
import re

# --- Fonctions de conversion (inchangées) ---
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
    return found_port

# --- Logique Principale d'Exécution (Entièrement Reconstruite) ---
def main():
    # 1. Récupérer et valider la séquence JSON
    if len(sys.argv) < 2:
        sys.exit(1)
    try:
        sequence = json.loads(sys.argv[1])
        if not isinstance(sequence, list):
            sys.exit(1)
    except (json.JSONDecodeError, IndexError):
        sys.exit(1)

    # 2. Trouver le port MIDI
    port_path = find_midi_port()
    if not port_path:
        sys.exit(1)
        
    # 3. Construire la "Partition" MIDI en mémoire
    # On crée une piste MIDI virtuelle pour y placer nos notes.
    track = mido.MidiTrack()
    
    # Mido a besoin de connaître la "vitesse" (ticks par noire).
    # Et la durée d'un tick en microsecondes (tempo).
    ticks_per_beat = 480 
    tempo = 500000  # Tempo par défaut (120 BPM)
    
    def seconds_to_ticks(seconds):
        return int(mido.second2tick(seconds, ticks_per_beat, tempo))

    for event in sequence:
        event_type = event.get("type", "").lower()
        duration_sec = float(event.get('duration', 0.5))
        duration_ticks = seconds_to_ticks(duration_sec)
        
        if event_type == 'note':
            note_name = event.get('note')
            midi_note = note_name_to_midi(note_name)
            if midi_note is None: continue
            
            velocity = int(event.get('velocity', 100))
            
            # Note ON (temps=0, car elle démarre immédiatement)
            track.append(mido.Message('note_on', note=midi_note, velocity=velocity, time=0))
            # Note OFF (temps = la durée de la note en ticks)
            track.append(mido.Message('note_off', note=midi_note, velocity=velocity, time=duration_ticks))
        
        elif event_type == 'chord':
            notes_in_chord = event.get('notes', [])
            if not notes_in_chord: continue

            # On allume toutes les notes de l'accord en même temps
            for i, note_info in enumerate(notes_in_chord):
                midi_note = note_name_to_midi(note_info.get('note'))
                if midi_note is None: continue
                velocity = int(note_info.get('velocity', 100))
                # La première note de l'accord a un délai de 0, les autres aussi.
                track.append(mido.Message('note_on', note=midi_note, velocity=velocity, time=0))
            
            # On éteint toutes les notes de l'accord après la durée voulue.
            # Seule la première note "off" porte la durée, les autres ont un délai de 0.
            for i, note_info in enumerate(notes_in_chord):
                midi_note = note_name_to_midi(note_info.get('note'))
                if midi_note is None: continue
                
                # Le premier message 'note_off' attend la durée de l'accord.
                # Les suivants s'exécutent immédiatement après.
                delay = duration_ticks if i == 0 else 0
                track.append(mido.Message('note_off', note=midi_note, time=delay))

    # 4. Jouer la partition sur le port MIDI
    try:
        with mido.open_output(port_path) as port:
            # La bibliothèque Mido gère elle-même le timing et l'envoi des messages.
            for msg in track:
                time.sleep(msg.time / ticks_per_beat * (tempo / 1000000.0))
                if not msg.is_meta:
                    port.send(msg)
    except Exception as e:
        # En cas d'erreur, enregistrer dans un log
        with open("fl_controller_error.log", "a") as f:
            f.write(f"{time.ctime()}: {str(e)}\n")
    finally:
        # Le script se termine proprement
        sys.exit(0)

if __name__ == "__main__":
    main()
