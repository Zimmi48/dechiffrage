import argparse
import select
import sys
import time
import mido
from music21 import converter, note, chord, stream

# Extraction des notes avec informations temporelles
FRENCH_NOTES = ["Do", "Do#", "Ré", "Ré#", "Mi", "Fa", "Fa#", "Sol", "Sol#", "La", "La#", "Si"]

def midi_to_french(pitch: int) -> str:
    name = FRENCH_NOTES[pitch % 12]
    octave = pitch // 12 - 1
    return f"{name}{octave}"

# Structure pour représenter un événement musical
# event_type: 'note' ou 'chord'
# pitches: liste des hauteurs MIDI
# duration: durée en quarter notes
# offset: position temporelle
class MusicEvent:
    def __init__(self, event_type, pitches, duration, offset, measure_num):
        self.type = event_type  # 'note' or 'chord'
        self.pitches = pitches  # list of MIDI pitches
        self.duration = duration  # quarterLength
        self.offset = offset  # temporal position
        self.measure = measure_num

    def __repr__(self):
        pitch_names = ", ".join(midi_to_french(p) for p in self.pitches)
        return f"{self.type.capitalize()}({pitch_names}, dur={self.duration:.2f})"

# Global state variables (will be initialized in main)
events = []
current_event_idx = 0
currently_pressed = set()
pending_chord_notes = set()
chord_start_time = None
CHORD_WINDOW = 0.5
notes_should_be_held = {}

def should_note_be_held(pitch, current_idx):
    """Détermine si une note devrait encore être tenue basé sur les événements précédents."""
    # Chercher la dernière occurrence de cette note avant l'événement actuel
    last_occurrence_idx = None
    for i in range(current_idx - 1, -1, -1):  # Recherche en arrière
        event = events[i]
        if pitch in event.pitches:
            last_occurrence_idx = i
            break  # On s'arrête à la première occurrence trouvée (la plus récente)

    if last_occurrence_idx is None:
        return False  # Cette note n'a jamais été jouée avant

    # Vérifier si la dernière occurrence se chevauche avec l'événement actuel
    last_event = events[last_occurrence_idx]
    if current_idx < len(events):
        current_event = events[current_idx]
        current_offset = float(current_event.offset)
        note_end_offset = float(last_event.offset + last_event.duration)
        last_offset = float(last_event.offset)

        # Si les deux événements commencent au même moment, pas de warning
        # (cela représente la même note dans différentes voix/durées en notation musicale)
        # Utiliser une petite tolérance pour les comparaisons flottantes
        if abs(last_offset - current_offset) < 1e-9:
            return False

        # Une note doit être tenue si elle se termine strictement après le début de l'événement suivant
        # Utiliser une tolérance pour éviter les problèmes d'arrondissement
        return note_end_offset > current_offset + 1e-9

    return False

def validate_note_held(pitch):
    """Vérifie qu'une note qui devrait être tenue est toujours enfoncée."""
    # Cherche dans les événements précédents si cette note devrait être tenue
    for i in range(current_event_idx):
        event = events[i]
        if pitch in event.pitches:
            # Note trouvée dans un événement précédent
            # Pour simplifier, on suppose qu'elle devrait être tenue si elle n'a pas été explicitement relâchée
            return True
    return False

def format_event(event):
    """Formatte un événement pour l'affichage."""
    if event.type == 'chord':
        notes = " + ".join(midi_to_french(p) for p in event.pitches)
        return f"Accord({notes})"
    else:
        return midi_to_french(event.pitches[0])

def check_event_completed(event):
    """Vérifie si un événement (note ou accord) est complété."""
    if event.type == 'note':
        # Une note simple est complétée si elle a été jouée
        return event.pitches[0] in currently_pressed
    else:  # chord
        # Un accord est complété si toutes ses notes sont jouées
        return all(p in currently_pressed for p in event.pitches)

def main():
    """Main function to run the MIDI validator"""
    global events, current_event_idx, currently_pressed, pending_chord_notes, chord_start_time, notes_should_be_held

    parser = argparse.ArgumentParser(description="MIDI piano validator")
    parser.add_argument("xml_file", help="Path to the MusicXML file")
    parser.add_argument(
        "--hand",
        choices=["left", "right", "both"],
        default="both",
        help="Which hand to validate (default: both)",
    )
    parser.add_argument(
        "--repeats",
        action="store_true",
        help="Expand repeat signs in the score (default: disabled)",
    )
    args = parser.parse_args()

    print("Chargement de la partition...")
    score = converter.parse(args.xml_file)

    # Expand repeats if requested
    if args.repeats:
        print("Expansion des répétitions...")
        score = score.expandRepeats()

    # Parts: index 0 = right hand, index 1 = left hand (standard grand staff)
    if args.hand == "right":
        parts = [score.parts[0]]
    elif args.hand == "left":
        parts = [score.parts[1]]
    else:
        parts = list(score.parts[:2])

    # Extraire les événements musicaux dans l'ordre temporel
    events = []
    for part in parts:
        # Utiliser flatten() pour obtenir les offsets absolus
        flat_part = part.flatten()
        for el in flat_part.notesAndRests:
            if isinstance(el, note.Note):
                # Utiliser l'offset absolu de l'élément dans la partie aplatie
                events.append(MusicEvent('note', [el.pitch.midi],
                                       el.duration.quarterLength,
                                       el.offset, el.measureNumber if hasattr(el, 'measureNumber') else 0))
            elif isinstance(el, chord.Chord):
                pitches = [p.midi for p in el.pitches]
                events.append(MusicEvent('chord', pitches,
                                       el.duration.quarterLength,
                                       el.offset, el.measureNumber if hasattr(el, 'measureNumber') else 0))

    # Trier par offset (ordre temporel) - les offsets sont maintenant absolus
    events.sort(key=lambda e: e.offset)

    # Fusionner les événements avec les mêmes pitches au même offset
    # (notes notées dans plusieurs voix avec des durées différentes)
    merged_events = []
    i = 0
    while i < len(events):
        current = events[i]
        # Chercher tous les événements au même offset avec des pitches qui se chevauchent
        same_offset_events = [current]
        j = i + 1
        while j < len(events) and abs(float(events[j].offset - current.offset)) < 1e-9:
            same_offset_events.append(events[j])
            j += 1

        # Grouper par pitch et garder la durée maximale pour chaque pitch
        pitch_to_max_duration = {}
        for event in same_offset_events:
            for pitch in event.pitches:
                if pitch not in pitch_to_max_duration:
                    pitch_to_max_duration[pitch] = event.duration
                else:
                    pitch_to_max_duration[pitch] = max(pitch_to_max_duration[pitch], event.duration)

        # Créer des événements fusionnés
        # Si plusieurs pitches au même offset, les regrouper en accord si possible
        processed_pitches = set()
        for event in same_offset_events:
            event_pitches = [p for p in event.pitches if p not in processed_pitches]
            if not event_pitches:
                continue

            # Utiliser la durée maximale pour chaque pitch
            max_duration = max(pitch_to_max_duration[p] for p in event_pitches)

            if len(event_pitches) == 1:
                merged_events.append(MusicEvent('note', event_pitches, max_duration,
                                               event.offset, event.measure))
            else:
                merged_events.append(MusicEvent('chord', event_pitches, max_duration,
                                               event.offset, event.measure))

            processed_pitches.update(event_pitches)

        i = j

    events = merged_events

    print(f"{len(events)} événements musicaux détectés (notes et accords).")
    if events:
        measures_count = max(e.measure for e in events)
        print(f"{measures_count} mesures couvrant ces événements.")
    print("Ouverture du port MIDI...")

    ports = mido.get_input_names()

    if not ports:
        print("Aucun port MIDI détecté.")
        exit()

    print("Ports disponibles :")

    for i, port in enumerate(ports):
        print(f"{i}: {port}")

    port_index = int(input("Sélectionnez le port MIDI : "))

    # État de validation
    current_event_idx = 0
    currently_pressed = set()  # Notes actuellement enfoncées (MIDI pitches)
    pending_chord_notes = set()  # Notes attendues pour compléter un accord
    chord_start_time = None  # Temps de début pour détecter un accord

    # Pour le suivi des notes tenues
    notes_should_be_held = {}  # {pitch: event_idx} - notes qui devraient être tenues

    try:
        with mido.open_input(ports[port_index]) as port:
            if not events:
                print("Aucun événement musical dans la partition.")
            else:
                current_event = events[current_event_idx]
                print(f"\nMesure {current_event.measure} / {measures_count}")
                print(f"Attendu: {format_event(current_event)}")
                print("Écoute en cours... (Ctrl+C, tapez 'q' pour quitter, ou 'j<numéro>' pour sauter à une mesure)\n")

            running = True
            while running:
                if current_event_idx >= len(events):
                    print("🎉 Pièce terminée.")
                    break

                ready, _, _ = select.select([sys.stdin], [], [], 0)
                if ready:
                    command = sys.stdin.readline().strip().lower()
                    if command in {"q", "quit"}:
                        print("\nArrêt de l'écoute.")
                        break
                    elif command.startswith("j"):
                        # Commande de saut vers une mesure spécifique
                        try:
                            # Extraire le numéro de mesure (après "j")
                            bar_str = command[1:].strip()
                            if bar_str:
                                target_bar = int(bar_str)
                                # Trouver le premier événement de cette mesure
                                found = False
                                for idx, event in enumerate(events):
                                    if event.measure == target_bar:
                                        current_event_idx = idx
                                        current_event = events[current_event_idx]
                                        currently_pressed.clear()
                                        chord_start_time = None
                                        pending_chord_notes = set()
                                        print(f"\n⏭  Saut vers mesure {target_bar}")
                                        print(f"Mesure {current_event.measure} / {measures_count}")
                                        print(f"Attendu: {format_event(current_event)}\n")
                                        found = True
                                        break
                                if not found:
                                    print(f"✗ Mesure {target_bar} introuvable (valide: 1-{measures_count})")
                            else:
                                print("✗ Usage: j<numéro> (exemple: j12 pour aller à la mesure 12)")
                        except ValueError:
                            print("✗ Numéro de mesure invalide. Usage: j<numéro> (exemple: j12)")

                for msg in port.iter_pending():
                    if msg.type == 'note_on' and msg.velocity > 0:
                        # Note enfoncée
                        pitch = msg.note
                        current_event = events[current_event_idx]

                        # Vérifier si la note fait partie de l'événement attendu
                        if pitch not in current_event.pitches:
                            # Note inattendue
                            print(f"✗ ERREUR : {midi_to_french(pitch)} inattendu")
                            print(f"  Attendu: {format_event(current_event)}")
                            continue

                        # Ajouter la note aux notes actuellement enfoncées
                        currently_pressed.add(pitch)
                        print(f"✓ OK {midi_to_french(pitch)}")

                        # Pour les accords, initialiser la fenêtre temporelle au premier note
                        if current_event.type == 'chord':
                            if chord_start_time is None:
                                chord_start_time = time.time()
                                pending_chord_notes = set(current_event.pitches) - {pitch}
                            else:
                                pending_chord_notes.discard(pitch)

                        # Vérifier si l'événement est complété
                        if check_event_completed(current_event):
                            # Avant de valider, vérifier que les notes qui doivent être tenues le sont
                            missing_held_notes = []
                            if current_event_idx > 0:  # Il y a des événements précédents
                                # Collecter tous les pitches uniques des événements précédents
                                checked_pitches = set()
                                for prev_idx in range(current_event_idx):
                                    prev_event = events[prev_idx]
                                    for prev_pitch in prev_event.pitches:
                                        # Ne vérifier chaque pitch qu'une seule fois
                                        if prev_pitch not in checked_pitches:
                                            checked_pitches.add(prev_pitch)
                                            if should_note_be_held(prev_pitch, current_event_idx):
                                                if prev_pitch not in currently_pressed:
                                                    missing_held_notes.append(prev_pitch)

                            if missing_held_notes:
                                note_names = ", ".join(midi_to_french(p) for p in missing_held_notes)
                                print(f"⚠ AVERTISSEMENT : Notes devraient être tenues : {note_names}")

                            if current_event.type == 'chord':
                                elapsed = time.time() - chord_start_time if chord_start_time else 0
                                if elapsed <= CHORD_WINDOW:
                                    print(f"✅ {format_event(current_event)} validé.\n")
                                    prev_measure = current_event.measure
                                    current_event_idx += 1
                                    chord_start_time = None
                                    pending_chord_notes = set()

                                    if current_event_idx < len(events):
                                        current_event = events[current_event_idx]
                                        # Afficher la mesure seulement si elle a changé
                                        if current_event.measure != prev_measure:
                                            print(f"Mesure {current_event.measure} / {measures_count}")
                                        print(f"Attendu: {format_event(current_event)}")
                                else:
                                    print(f"✗ ERREUR : Accord trop lent (>{CHORD_WINDOW}s)")
                                    # Réinitialiser pour réessayer
                                    chord_start_time = None
                                    pending_chord_notes = set(current_event.pitches)
                                    currently_pressed.clear()
                            else:  # note simple
                                print(f"✅ {format_event(current_event)} validé.\n")
                                prev_measure = current_event.measure
                                current_event_idx += 1

                                if current_event_idx < len(events):
                                    current_event = events[current_event_idx]
                                    # Afficher la mesure seulement si elle a changé
                                    if current_event.measure != prev_measure:
                                        print(f"Mesure {current_event.measure} / {measures_count}")
                                    print(f"Attendu: {format_event(current_event)}")

                    elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                        # Note relâchée
                        pitch = msg.note
                        currently_pressed.discard(pitch)

                        # Vérifier si une note qui devrait être tenue a été relâchée prématurément
                        # (Pour l'instant, on ne valide pas strictement la durée des notes)

                time.sleep(0.01)
    except KeyboardInterrupt:
        print("\n\nArrêt de l'écoute.")
        sys.exit(0)

if __name__ == "__main__":
    main()
