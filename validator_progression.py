import argparse
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
print("Ports disponibles :", ports)

if not ports:
    print("Aucun port MIDI détecté.")
    exit()

current_measure = 0
played_notes = []

def measure_completed(expected, played):
    # compare en multiensemble (ignore ordre)
    exp = expected.copy()
    for p in played:
        if p in exp:
            exp.remove(p)
    return len(exp) == 0

with mido.open_input(ports[-1]) as port:
    print(f"\nMesure 1 / {len(measures)}")
    print("Écoute en cours...\n")

    for msg in port:
        if msg.type == 'note_on' and msg.velocity > 0:

            if current_measure >= len(measures):
                print("🎉 Pièce terminée.")
                break

            pitch = msg.note
            expected = measures[current_measure]

            if pitch not in expected:
                print(f"✗ ERREUR mesure {current_measure+1} : {pitch}")
            else:
                played_notes.append(pitch)
                print(f"✓ OK {pitch}")

                if measure_completed(expected, played_notes):
                    print(f"✅ Mesure {current_measure+1} validée.\n")
                    current_measure += 1
                    played_notes = []

                    if current_measure < len(measures):
                        print(f"Mesure {current_measure+1} / {len(measures)}")