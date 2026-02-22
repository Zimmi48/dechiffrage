import argparse
import select
import sys
import time
import mido
from music21 import converter, note, chord, stream

parser = argparse.ArgumentParser(description="MIDI piano validator")
parser.add_argument("xml_file", help="Path to the MusicXML file")
parser.add_argument(
    "--hand",
    choices=["left", "right", "both"],
    default="both",
    help="Which hand to validate (default: both)",
)
args = parser.parse_args()

print("Chargement de la partition...")
score = converter.parse(args.xml_file)

# Parts: index 0 = right hand, index 1 = left hand (standard grand staff)
if args.hand == "right":
    parts = [score.parts[0]]
elif args.hand == "left":
    parts = [score.parts[1]]
else:
    parts = list(score.parts[:2])

# Extraction des notes par mesure (merge across selected parts)
FRENCH_NOTES = ["Do", "Do#", "Ré", "Ré#", "Mi", "Fa", "Fa#", "Sol", "Sol#", "La", "La#", "Si"]

def midi_to_french(pitch: int) -> str:
    name = FRENCH_NOTES[pitch % 12]
    octave = pitch // 12 - 1
    return f"{name}{octave}"

measure_map: dict[int, list[int]] = {}
for part in parts:
    for m in part.getElementsByClass(stream.Measure):
        expected = measure_map.setdefault(m.number, [])
        for el in m.recurse():
            if isinstance(el, note.Note):
                expected.append(el.pitch.midi)
            elif isinstance(el, chord.Chord):
                for p in el.pitches:
                    expected.append(p.midi)

measures = [notes for _, notes in sorted(measure_map.items()) if notes]
print(f"{len(measures)} mesures détectées.")
print("Ouverture du port MIDI...")

ports = mido.get_input_names()

if not ports:
    print("Aucun port MIDI détecté.")
    exit()

print("Ports disponibles :")

for i, port in enumerate(ports):
    print(f"{i}: {port}")

port_index = int(input("Sélectionnez le port MIDI : "))

current_measure = 0
played_notes = []

def measure_completed(expected, played):
    # compare en multiensemble (ignore ordre)
    exp = expected.copy()
    for p in played:
        if p in exp:
            exp.remove(p)
    return len(exp) == 0

try:
    with mido.open_input(ports[port_index]) as port:
        print(f"\nMesure 1 / {len(measures)}")
        print("Écoute en cours... (Ctrl+C ou tapez q puis Entrée pour quitter)")
        print("Commandes : j = mesure actuelle, j<numéro> = aller à la mesure\n")

        running = True
        while running:
            if current_measure >= len(measures):
                print("🎉 Pièce terminée.")
                break

            ready, _, _ = select.select([sys.stdin], [], [], 0)
            if ready:
                command = sys.stdin.readline().strip().lower()
                if command in {"q", "quit"}:
                    print("\nArrêt de l'écoute.")
                    break
                elif command.startswith("j"):
                    # Handle jump to bar: j alone shows current, j<number> jumps to that bar
                    if command == "j":
                        print(f"Mesure actuelle : {current_measure+1} / {len(measures)}")
                    else:
                        try:
                            target_measure = int(command[1:])
                            if 1 <= target_measure <= len(measures):
                                current_measure = target_measure - 1
                                played_notes = []
                                print(f"Passage à la mesure {current_measure+1} / {len(measures)}")
                            else:
                                print(f"Erreur : mesure {target_measure} hors de portée (1-{len(measures)})")
                        except ValueError:
                            print(f"Erreur : commande invalide '{command}'. Utilisez 'j' ou 'j<numéro>'.")

            for msg in port.iter_pending():
                if msg.type != 'note_on' or msg.velocity <= 0:
                    continue

                pitch = msg.note
                expected = measures[current_measure]

                if pitch not in expected:
                    print(f"✗ ERREUR mesure {current_measure+1} : {midi_to_french(pitch)}")
                    continue

                played_notes.append(pitch)
                print(f"✓ OK {midi_to_french(pitch)}")

                if measure_completed(expected, played_notes):
                    print(f"✅ Mesure {current_measure+1} validée.\n")
                    current_measure += 1
                    played_notes = []

                    if current_measure < len(measures):
                        print(f"Mesure {current_measure+1} / {len(measures)}")

            time.sleep(0.01)
except KeyboardInterrupt:
    print("\n\nArrêt de l'écoute.")
    sys.exit(0)