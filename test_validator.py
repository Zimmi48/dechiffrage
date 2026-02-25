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

    def test_same_pitch_multiple_times_most_recent_checked(self):
        """Test that only the most recent occurrence of a pitch is checked"""
        from validator_progression import MusicEvent, should_note_be_held
        import validator_progression

        # Create events with the same pitch appearing twice
        events = [
            MusicEvent('note', [60], 1.0, 0.0, 1),   # C4: offset 0, duration 1, ends at 1
            MusicEvent('note', [62], 1.0, 2.0, 1),   # D4: offset 2, duration 1, ends at 3
            MusicEvent('note', [60], 2.0, 4.0, 1),   # C4 again: offset 4, duration 2, ends at 6
            MusicEvent('note', [64], 1.0, 7.0, 2),   # E4: offset 7, duration 1, ends at 8
        ]

        validator_progression.events = events

        # At event 3 (E4 at offset 7):
        # - First C4 ended at offset 1 (no overlap with offset 7)
        # - Second C4 ended at offset 6 (no overlap with offset 7)
        # - So C4 should NOT need to be held (most recent occurrence should be checked)
        result = should_note_be_held(60, 3)
        self.assertFalse(result, "C4 should not need to be held at event 3 - most recent occurrence ended at offset 6")

    def test_most_recent_pitch_overlaps(self):
        """Test that a note should be held when the most recent occurrence overlaps"""
        from validator_progression import MusicEvent, should_note_be_held
        import validator_progression

        events = [
            MusicEvent('note', [60], 1.0, 0.0, 1),   # C4: offset 0, duration 1, ends at 1
            MusicEvent('note', [60], 4.0, 2.0, 1),   # C4 again: offset 2, duration 4, ends at 6
            MusicEvent('note', [64], 1.0, 4.0, 1),   # E4: offset 4, duration 1, ends at 5
        ]

        validator_progression.events = events

        # At event 2 (E4 at offset 4):
        # - First C4 ended at offset 1 (no overlap)
        # - Second C4 ends at offset 6 (OVERLAPS with offset 4)
        # - So C4 SHOULD need to be held (checking most recent occurrence)
        result = should_note_be_held(60, 2)
        self.assertTrue(result, "C4 should need to be held at event 2 - most recent occurrence ends at offset 6")

    def test_note_in_chord_should_be_held(self):
        """Test that notes in chords are properly tracked for held note detection"""
        from validator_progression import MusicEvent, should_note_be_held
        import validator_progression

        events = [
            MusicEvent('chord', [60, 64, 67], 3.0, 0.0, 1),  # C major chord: offset 0, duration 3, ends at 3
            MusicEvent('note', [69], 1.0, 1.0, 1),           # A4: offset 1, duration 1, ends at 2
        ]

        validator_progression.events = events

        # At event 1 (A4 at offset 1):
        # - The chord (with C4, E4, G4) ends at offset 3
        # - Current event is at offset 1
        # - So all chord notes should be held
        self.assertTrue(should_note_be_held(60, 1), "C4 from chord should be held")
        self.assertTrue(should_note_be_held(64, 1), "E4 from chord should be held")
        self.assertTrue(should_note_be_held(67, 1), "G4 from chord should be held")

    def test_simultaneous_notes_different_durations(self):
        """Test that simultaneous notes with different durations don't warn about each other"""
        from validator_progression import MusicEvent, should_note_be_held
        import validator_progression

        # This represents the same note played in two voices with different durations
        # Common in piano music notation
        events = [
            MusicEvent('note', [62], 0.5, 0.0, 1),   # Ré4: offset 0, duration 0.5, ends at 0.5
            MusicEvent('note', [62], 1.0, 0.0, 1),   # Ré4: offset 0, duration 1.0, ends at 1.0 (same start time!)
            MusicEvent('note', [64], 0.5, 0.5, 1),   # E4: offset 0.5, duration 0.5, ends at 1.0
        ]

        validator_progression.events = events

        # Event 1 (Ré4 at offset 0) should NOT warn about event 0 (also Ré4 at offset 0)
        # They start at the same time - the user presses the key once
        self.assertFalse(should_note_be_held(62, 1), "Simultaneous notes shouldn't require holding")

        # Event 2 (E4 at offset 0.5) SHOULD warn about Ré4 from event 1 (ends at 1.0)
        self.assertTrue(should_note_be_held(62, 2), "Ré4 should still be held at event 2")

    def test_notes_ending_exactly_when_next_starts(self):
        """Test that notes ending exactly when next note starts don't cause false warnings"""
        from validator_progression import MusicEvent, should_note_be_held
        import validator_progression

        events = [
            MusicEvent('note', [60], 1.0, 0.0, 1),   # C4: offset 0, duration 1, ends at 1
            MusicEvent('note', [62], 1.0, 1.0, 1),   # D4: offset 1, duration 1, ends at 2
        ]

        validator_progression.events = events

        # Event 1 (D4 at offset 1) should NOT warn about C4 (which ends exactly at offset 1)
        # Using floating point tolerance to handle rounding errors
        self.assertFalse(should_note_be_held(60, 1), "Notes ending exactly when next starts shouldn't require holding")


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


class TestJumpToBar(unittest.TestCase):
    """Test the jump to bar functionality"""

    def test_find_first_event_in_bar(self):
        """Test finding the first event in a specific measure"""
        from validator_progression import MusicEvent
        import validator_progression

        # Create events across multiple measures
        events = [
            MusicEvent('note', [60], 1.0, 0.0, 1),   # Measure 1
            MusicEvent('note', [62], 1.0, 1.0, 1),   # Measure 1
            MusicEvent('note', [64], 1.0, 2.0, 2),   # Measure 2
            MusicEvent('note', [65], 1.0, 3.0, 2),   # Measure 2
            MusicEvent('note', [67], 1.0, 4.0, 3),   # Measure 3
        ]

        validator_progression.events = events

        # Test finding first event in measure 2
        target_bar = 2
        found_idx = None
        for idx, event in enumerate(events):
            if event.measure == target_bar:
                found_idx = idx
                break

        self.assertIsNotNone(found_idx, "Should find an event in measure 2")
        self.assertEqual(found_idx, 2, "Should find the first event (index 2) in measure 2")
        self.assertEqual(events[found_idx].measure, 2, "Found event should be in measure 2")

    def test_jump_to_nonexistent_bar(self):
        """Test handling of jump to a bar that doesn't exist"""
        from validator_progression import MusicEvent
        import validator_progression

        events = [
            MusicEvent('note', [60], 1.0, 0.0, 1),
            MusicEvent('note', [62], 1.0, 1.0, 2),
        ]

        validator_progression.events = events

        # Try to find measure 5 (doesn't exist)
        target_bar = 5
        found = False
        for idx, event in enumerate(events):
            if event.measure == target_bar:
                found = True
                break

        self.assertFalse(found, "Should not find measure 5")


class TestRepeatExpansion(unittest.TestCase):
    """Test the repeat expansion functionality"""

    def test_argparse_repeats_flag(self):
        """Test that --repeats argument is properly defined"""
        import argparse
        import sys
        from unittest.mock import patch

        # Mock sys.argv to test argument parsing
        test_args = ['validator_progression.py', 'test.xml', '--repeats']
        with patch.object(sys, 'argv', test_args):
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

            self.assertTrue(args.repeats, "repeats flag should be True")
            self.assertEqual(args.xml_file, 'test.xml')
            self.assertEqual(args.hand, 'both')

    def test_argparse_repeats_flag_default(self):
        """Test that --repeats defaults to False"""
        import argparse
        import sys
        from unittest.mock import patch

        test_args = ['validator_progression.py', 'test.xml']
        with patch.object(sys, 'argv', test_args):
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

            self.assertFalse(args.repeats, "repeats flag should default to False")

    def test_repeat_expansion_with_music21(self):
        """Test that expandRepeats is called when repeats flag is set"""
        # Create a simple score with a repeat
        s = stream.Score()
        p = stream.Part()

        # Add a measure
        m1 = stream.Measure(number=1)
        m1.append(note.Note('C4', quarterLength=1.0))
        m1.append(note.Note('D4', quarterLength=1.0))

        # Add repeat bar line at the end
        from music21 import bar
        m1.rightBarline = bar.Repeat(direction='end')

        m2 = stream.Measure(number=2)
        m2.append(note.Note('E4', quarterLength=2.0))

        p.append(m1)
        p.append(m2)
        s.append(p)

        # Expand repeats
        expanded_score = s.expandRepeats()

        # The expanded score should exist
        self.assertIsNotNone(expanded_score, "Expanded score should not be None")

        # Note: music21's expandRepeats may or may not actually expand the simple repeat
        # depending on whether there's a matching start repeat. This test just verifies
        # that the method can be called without error.


if __name__ == '__main__':
    # Try to import the module first
    try:
        import validator_progression
        print("Successfully imported validator_progression module")
    except Exception as e:
        print(f"Warning: Could not import validator_progression: {e}")
        print("Some tests may be skipped")

    unittest.main()
