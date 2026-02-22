#!/usr/bin/env python3
"""Tests for validator_progression.py"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from music21 import note, chord, stream, converter
import tempfile
import os


# Import the functions and classes we need to test
# We'll need to refactor validator_progression.py to make it more testable
# For now, we'll test the core logic functions


class TestMusicEvent(unittest.TestCase):
    """Test the MusicEvent class"""

    def test_note_event_creation(self):
        """Test creating a note event"""
        from validator_progression import MusicEvent, midi_to_french

        event = MusicEvent('note', [60], 1.0, 0.0, 1)
        self.assertEqual(event.type, 'note')
        self.assertEqual(event.pitches, [60])
        self.assertEqual(event.duration, 1.0)
        self.assertEqual(event.offset, 0.0)
        self.assertEqual(event.measure, 1)

    def test_chord_event_creation(self):
        """Test creating a chord event"""
        from validator_progression import MusicEvent

        event = MusicEvent('chord', [60, 64, 67], 2.0, 4.0, 2)
        self.assertEqual(event.type, 'chord')
        self.assertEqual(len(event.pitches), 3)
        self.assertIn(60, event.pitches)
        self.assertIn(64, event.pitches)
        self.assertIn(67, event.pitches)


class TestMidiToFrench(unittest.TestCase):
    """Test MIDI to French note name conversion"""

    def test_midi_to_french(self):
        """Test converting MIDI pitches to French note names"""
        from validator_progression import midi_to_french

        # Test C4 (middle C)
        self.assertEqual(midi_to_french(60), "Do4")

        # Test C#4
        self.assertEqual(midi_to_french(61), "Do#4")

        # Test D4
        self.assertEqual(midi_to_french(62), "Ré4")

        # Test D#4
        self.assertEqual(midi_to_french(63), "Ré#4")

        # Test E4
        self.assertEqual(midi_to_french(64), "Mi4")

        # Test F4
        self.assertEqual(midi_to_french(65), "Fa4")

        # Test F#4
        self.assertEqual(midi_to_french(66), "Fa#4")

        # Test G4
        self.assertEqual(midi_to_french(67), "Sol4")

        # Test G#4
        self.assertEqual(midi_to_french(68), "Sol#4")

        # Test A4
        self.assertEqual(midi_to_french(69), "La4")

        # Test A#4
        self.assertEqual(midi_to_french(70), "La#4")

        # Test B4
        self.assertEqual(midi_to_french(71), "Si4")

        # Test C5
        self.assertEqual(midi_to_french(72), "Do5")

        # Test lower octave C3
        self.assertEqual(midi_to_french(48), "Do3")


class TestEventExtraction(unittest.TestCase):
    """Test event extraction from MusicXML"""

    def test_note_extraction_order(self):
        """Test that notes are extracted in correct temporal order"""
        # Create a simple score with notes
        s = stream.Score()
        p = stream.Part()

        # Add measures with notes
        m1 = stream.Measure(number=1)
        m1.append(note.Note('C4', quarterLength=1.0))
        m1.append(note.Note('D4', quarterLength=1.0))

        m2 = stream.Measure(number=2)
        m2.append(note.Note('E4', quarterLength=2.0))

        p.append(m1)
        p.append(m2)
        s.append(p)

        # Extract events as the code does
        from validator_progression import MusicEvent

        events = []
        flat_part = p.flatten()
        for el in flat_part.notesAndRests:
            if isinstance(el, note.Note):
                events.append(MusicEvent('note', [el.pitch.midi],
                                       el.duration.quarterLength,
                                       el.offset, el.measureNumber if hasattr(el, 'measureNumber') else 0))

        events.sort(key=lambda e: e.offset)

        # Check we got 3 events
        self.assertEqual(len(events), 3)

        # Check they're in the right order
        self.assertEqual(events[0].pitches[0], 60)  # C4
        self.assertEqual(events[1].pitches[0], 62)  # D4
        self.assertEqual(events[2].pitches[0], 64)  # E4

        # Check offsets are increasing
        self.assertLess(events[0].offset, events[1].offset)
        self.assertLess(events[1].offset, events[2].offset)

    def test_chord_extraction(self):
        """Test that chords are extracted correctly"""
        # Create a score with a chord
        s = stream.Score()
        p = stream.Part()
        m = stream.Measure(number=1)

        # Add a C major chord
        c_chord = chord.Chord(['C4', 'E4', 'G4'])
        c_chord.quarterLength = 1.0
        m.append(c_chord)

        p.append(m)
        s.append(p)

        # Extract events
        from validator_progression import MusicEvent

        events = []
        flat_part = p.flatten()
        for el in flat_part.notesAndRests:
            if isinstance(el, chord.Chord):
                pitches = [pitch.midi for pitch in el.pitches]
                events.append(MusicEvent('chord', pitches,
                                       el.duration.quarterLength,
                                       el.offset, el.measureNumber if hasattr(el, 'measureNumber') else 0))

        # Check we got 1 chord event
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type, 'chord')

        # Check it has 3 pitches (C, E, G)
        self.assertEqual(len(events[0].pitches), 3)
        self.assertIn(60, events[0].pitches)  # C4
        self.assertIn(64, events[0].pitches)  # E4
        self.assertIn(67, events[0].pitches)  # G4


class TestShouldNoteBeHeld(unittest.TestCase):
    """Test the should_note_be_held function"""

    def test_note_should_be_held(self):
        """Test detecting when a note should be held"""
        from validator_progression import MusicEvent, should_note_be_held

        # Create events: a long note followed by a short note
        # The long note should still be held when the short note plays
        events = [
            MusicEvent('note', [60], 4.0, 0.0, 1),  # Long C4 note (4 beats)
            MusicEvent('note', [62], 1.0, 1.0, 1),  # Short D4 note (1 beat) starting at beat 1
        ]

        # Make events available globally for the function
        import validator_progression
        validator_progression.events = events

        # Check if C4 (pitch 60) should be held when we're at event 1 (the D4)
        # The C4 starts at offset 0 and lasts 4 beats, so it should still be held at offset 1
        self.assertTrue(should_note_be_held(60, 1))

        # Check that D4 (pitch 62) should not be held (it hasn't started yet)
        # Actually, at index 1, we're ON the D4, so this test needs adjustment
        # Let's test a note that definitely shouldn't be held
        self.assertFalse(should_note_be_held(64, 1))  # E4 never played

    def test_note_should_not_be_held_after_duration(self):
        """Test that notes are not required to be held after their duration"""
        from validator_progression import MusicEvent, should_note_be_held

        # Create events: a short note followed by a later note
        events = [
            MusicEvent('note', [60], 1.0, 0.0, 1),  # Short C4 note (1 beat)
            MusicEvent('note', [62], 1.0, 2.0, 1),  # D4 note starting at beat 2
        ]

        import validator_progression
        validator_progression.events = events

        # At event 1 (D4 at offset 2), the C4 (which ended at offset 1) should not need to be held
        self.assertFalse(should_note_be_held(60, 1))


class TestFormatEvent(unittest.TestCase):
    """Test the format_event function"""

    def test_format_single_note(self):
        """Test formatting a single note event"""
        from validator_progression import MusicEvent, format_event

        event = MusicEvent('note', [60], 1.0, 0.0, 1)
        formatted = format_event(event)
        self.assertEqual(formatted, "Do4")

    def test_format_chord(self):
        """Test formatting a chord event"""
        from validator_progression import MusicEvent, format_event

        event = MusicEvent('chord', [60, 64, 67], 1.0, 0.0, 1)
        formatted = format_event(event)
        self.assertIn("Accord", formatted)
        self.assertIn("Do4", formatted)
        self.assertIn("Mi4", formatted)
        self.assertIn("Sol4", formatted)


class TestCheckEventCompleted(unittest.TestCase):
    """Test the check_event_completed function"""

    def test_single_note_completed(self):
        """Test checking if a single note is completed"""
        from validator_progression import MusicEvent, check_event_completed
        import validator_progression

        event = MusicEvent('note', [60], 1.0, 0.0, 1)

        # Note not pressed yet
        validator_progression.currently_pressed = set()
        self.assertFalse(check_event_completed(event))

        # Note is pressed
        validator_progression.currently_pressed = {60}
        self.assertTrue(check_event_completed(event))

    def test_chord_completed(self):
        """Test checking if a chord is completed"""
        from validator_progression import MusicEvent, check_event_completed
        import validator_progression

        event = MusicEvent('chord', [60, 64, 67], 1.0, 0.0, 1)

        # No notes pressed
        validator_progression.currently_pressed = set()
        self.assertFalse(check_event_completed(event))

        # Only one note pressed
        validator_progression.currently_pressed = {60}
        self.assertFalse(check_event_completed(event))

        # Two notes pressed
        validator_progression.currently_pressed = {60, 64}
        self.assertFalse(check_event_completed(event))

        # All three notes pressed
        validator_progression.currently_pressed = {60, 64, 67}
        self.assertTrue(check_event_completed(event))

        # All three notes plus extra notes pressed
        validator_progression.currently_pressed = {60, 64, 67, 69}
        self.assertTrue(check_event_completed(event))


if __name__ == '__main__':
    # Try to import the module first
    try:
        import validator_progression
        print("Successfully imported validator_progression module")
    except Exception as e:
        print(f"Warning: Could not import validator_progression: {e}")
        print("Some tests may be skipped")

    unittest.main()
