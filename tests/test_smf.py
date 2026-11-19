
import math
import os
import struct
from io import BytesIO

from mutagen.smf import SMF, SMFError
from tests import TestCase, DATA_DIR


def _var_int(value):
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append(0x80 | (value & 0x7F))
        value >>= 7
    return bytes(reversed(out))


def _chunk(identifier, body):
    return identifier + struct.pack(">I", len(body)) + body


def _header(format_, ntracks, division):
    return _chunk(b"MThd", struct.pack(">HHH", format_, ntracks, division))


def _track(events):
    return _chunk(b"MTrk", b"".join(_var_int(delta) + data
                                    for delta, data in events))


def _note(delta=0, on=True, note=60, channel=0):
    status = (0x90 if on else 0x80) | channel
    return delta, bytes([status, note, 64 if on else 0])


def _end_of_track(delta=0):
    return delta, b"\xff\x2f\x00"


def _tempo(delta, microseconds):
    return (delta, b"\xff\x51\x03" +
            struct.pack(">I", microseconds)[1:])


def _time_signature(delta, numerator=4, denominator=4):
    return delta, bytes([0xFF, 0x58, 0x04, numerator,
                         int(math.log(denominator, 2)), 24, 8])


def _smf(division, *tracks, format_=None):
    format_ = len(tracks) - 1 if format_ is None else format_
    return _header(format_, len(tracks), division) + b"".join(tracks)


class TSMF(TestCase):

    def setUp(self):
        self.audio = SMF(os.path.join(DATA_DIR, "sample.mid"))

    def test_length(self):
        self.failUnlessAlmostEqual(self.audio.info.length, 127.997, 2)

    def test_not_my_file(self):
        self.failUnlessRaises(
            SMFError, SMF, os.path.join(DATA_DIR, "empty.ogg"))

    def test_pprint(self):
        self.audio.pprint()
        self.audio.info.pprint()

    def test_mime(self):
        self.assertTrue("audio/x-midi" in self.audio.mime)
        self.assertTrue("audio/midi" in self.audio.mime)


class TSMFLength(TestCase):
    """Duration calculation for metric and SMPTE time divisions"""

    def _length(self, data):
        return SMF(BytesIO(data)).info.length

    def test_default_tempo(self):
        # 480 ticks per quarter, default 120 BPM (500000 us): two quarters
        data = _smf(480, _track([
            _note(480), _note(480, on=False), _end_of_track()]))
        self.assertAlmostEqual(self._length(data), 1.0)

    def test_trailing_meta_delta_does_not_extend_metric_duration(self):
        # the end-of-track delta is not a MIDI event, so the song ends at
        # the last MIDI event (preserves the behavior for old files)
        data = _smf(480, _track([
            _note(480), _note(480, on=False), _end_of_track(480)]))
        self.assertAlmostEqual(self._length(data), 1.0)

    def test_tempo_changes_format_0(self):
        # 240 BPM for the first quarter (0.25 s) then 60 BPM (1.0 s)
        data = _smf(480, _track([
            _tempo(0, 250000), _note(480), _tempo(0, 1000000),
            _note(480, on=False), _end_of_track()]))
        self.assertAlmostEqual(self._length(data), 1.25)

    def test_tempo_changes_format_1(self):
        # tempo map lives in the first (tempo only) track
        tempo_track = _track([
            _tempo(0, 250000), _tempo(480, 1000000), _end_of_track()])
        note_track = _track([
            _note(480), _note(480, on=False), _end_of_track()])
        data = _smf(480, tempo_track, note_track)
        self.assertAlmostEqual(self._length(data), 1.25)

    def test_tempo_after_last_midi_event_ignored(self):
        data = _smf(480, _track([
            _note(480), _note(480, on=False),
            _tempo(0, 1000000), _end_of_track()]))
        self.assertAlmostEqual(self._length(data), 1.0)

    def test_tempo_in_second_track_is_considered(self):
        # a non standard file placing the tempo map outside the first track
        empty_track = _track([_end_of_track()])
        tempo_track = _track([
            _tempo(0, 250000), _note(480), _note(480, on=False),
            _end_of_track()])
        data = _smf(480, empty_track, tempo_track, format_=1)
        # two quarters at 240 BPM (250000 us each) -> 0.5 s
        self.assertAlmostEqual(self._length(data), 0.5)

    def test_tempo_change_inside_second_track_is_considered(self):
        empty_track = _track([_end_of_track()])
        tempo_track = _track([
            _tempo(0, 250000), _note(480), _tempo(0, 1000000),
            _note(480, on=False), _end_of_track()])
        data = _smf(480, empty_track, tempo_track, format_=1)
        self.assertAlmostEqual(self._length(data), 1.25)

    def test_tempo_at_non_zero_tick_in_single_track_format_1(self):
        # regression: the old timeline reset logic treated a tempo change
        # later in the only track as if it happened at tick zero, so the
        # ticks before it were timed with the new tempo
        data = _smf(960, _track([
            _note(239), _tempo(0, 1000000), _note(475, on=False),
            _end_of_track()]), format_=1)
        # 239 ticks at 120 BPM + 475 ticks at 60 BPM
        expected = 239 / 960 * 0.5 + 475 / 960
        self.assertAlmostEqual(self._length(data), expected)

    def test_time_signature_changes(self):
        # time signature is notation only and must not change the duration
        data = _smf(480, _track([
            _time_signature(0, 4, 4), _note(480),
            _time_signature(0, 3, 4), _note(480, on=False),
            _end_of_track()]))
        self.assertAlmostEqual(self._length(data), 1.0)

    def test_multi_track_takes_longest(self):
        short_track = _track([
            _note(240), _note(240, on=False), _end_of_track()])
        long_track = _track([
            _note(960), _note(960, on=False), _end_of_track()])
        data = _smf(480, short_track, long_track)
        self.assertAlmostEqual(self._length(data), 2.0)

    def test_concurrent_events_same_tick(self):
        tracks = [_track([
            _note(480), _note(0, on=False), _end_of_track()])
            for _ in range(3)]
        data = _smf(480, *tracks, format_=1)
        self.assertAlmostEqual(self._length(data), 0.5)

    def test_zero_length_metric(self):
        data = _smf(480, _track([_end_of_track()]))
        self.assertEqual(self._length(data), 0.0)

    def test_zero_length_multi_track(self):
        tracks = [_track([_end_of_track()]) for _ in range(2)]
        data = _smf(480, *tracks)
        self.assertEqual(self._length(data), 0.0)

    def test_meta_only_track_does_not_add_duration(self):
        tempo_track = _track([_tempo(0, 250000), _end_of_track()])
        note_track = _track([
            _note(480), _note(0, on=False), _end_of_track()])
        data = _smf(480, tempo_track, note_track)
        self.assertAlmostEqual(self._length(data), 0.25)

    def test_system_exclusive_and_running_status(self):
        data = _smf(480, _track([
            (0, b"\xf0\x03\x01\x02\x03"),
            _note(480),
            (0, b"\x3c\x40"),
            _note(480, on=False),
            _end_of_track()]))
        self.assertAlmostEqual(self._length(data), 1.0)


class TSMFSMPTE(TestCase):
    """SMPTE (frame based) time division"""

    def _length(self, data):
        return SMF(BytesIO(data)).info.length

    def test_smpte_duration_25fps(self):
        # 25 fps, 40 subframes per frame -> 1000 ticks per second
        division = (0xE7 << 8) | 40
        data = _smf(division, _track([
            _note(400), _note(600, on=False), _end_of_track()]))
        self.assertAlmostEqual(self._length(data), 1.0)

    def test_smpte_duration_30fps(self):
        division = (0xE2 << 8) | 10
        data = _smf(division, _track([
            _note(300), _end_of_track()]))
        self.assertAlmostEqual(self._length(data), 1.0)

    def test_smpte_duration_2997fps(self):
        division = (0xE3 << 8) | 100
        data = _smf(division, _track([
            _note(2997), _end_of_track()]))
        self.assertAlmostEqual(self._length(data), 1.0)

    def test_smpte_duration_24fps(self):
        division = (0xE8 << 8) | 25
        data = _smf(division, _track([
            _note(600), _end_of_track()]))
        self.assertAlmostEqual(self._length(data), 1.0)

    def test_smpte_trailing_meta_delta_counts(self):
        # unlike metric division, the end-of-track delta advances SMPTE time
        division = (0xE7 << 8) | 40
        data = _smf(division, _track([
            _note(400), _note(500, on=False), _end_of_track(100)]))
        self.assertAlmostEqual(self._length(data), 1.0)

    def test_smpte_tempo_events_are_ignored(self):
        division = (0xE8 << 8) | 25
        data = _smf(division, _track([
            _tempo(0, 1000000), _note(300), _end_of_track(300)]))
        self.assertAlmostEqual(self._length(data), 600 / (24.0 * 25))

    def test_smpte_multi_track_takes_longest(self):
        division = (0xE7 << 8) | 40
        short_track = _track([_note(250), _end_of_track()])
        long_track = _track([_note(1000), _end_of_track()])
        data = _smf(division, short_track, long_track)
        self.assertAlmostEqual(self._length(data), 1.0)

    def test_smpte_zero_length(self):
        division = (0xE7 << 8) | 40
        data = _smf(division, _track([_end_of_track()]))
        self.assertEqual(self._length(data), 0.0)

    def test_smpte_unknown_frame_rate(self):
        division = (0xE0 << 8) | 40
        data = _smf(division, _track([_end_of_track()]))
        self.failUnlessRaises(SMFError, SMF, BytesIO(data))

    def test_smpte_zero_ticks_per_frame(self):
        division = 0xE7 << 8
        data = _smf(division, _track([_end_of_track()]))
        self.failUnlessRaises(SMFError, SMF, BytesIO(data))


class TSMFErrors(TestCase):
    """Corrupt files raise SMFError with a locate-able message"""

    def _assert_error(self, data, message_fragment):
        try:
            SMF(BytesIO(data))
        except SMFError as e:
            self.assertTrue(message_fragment in str(e), str(e))
            # track and offset are reported so the event can be located
            self.assertTrue("Track 1" in str(e), str(e))
            self.assertTrue("offset" in str(e), str(e))
        else:
            self.fail("SMFError not raised")

    def test_truncated_midi_event(self):
        data = _smf(480, _chunk(b"MTrk", b"\x00\x90\x3c"))
        self._assert_error(data, "truncated MIDI event")

    def test_running_status_without_previous_event(self):
        data = _smf(480, _chunk(b"MTrk", b"\x00\x3c\x40"))
        self._assert_error(data, "running status")

    def test_invalid_status_byte(self):
        data = _smf(480, _chunk(b"MTrk", b"\x00\xf2\x00"))
        self._assert_error(data, "invalid event")

    def test_truncated_meta_event(self):
        data = _smf(480, _chunk(b"MTrk", b"\x00\xff\x02\x05abc"))
        self._assert_error(data, "meta event")

    def test_bad_tempo_payload_length(self):
        data = _smf(480, _chunk(b"MTrk", b"\x00\xff\x51\x02\x10\x20"))
        self._assert_error(data, "tempo event")

    def test_zero_tempo(self):
        data = _smf(480, _chunk(b"MTrk", b"\x00\xff\x51\x03\x00\x00\x00"))
        self._assert_error(data, "tempo")

    def test_truncated_system_exclusive(self):
        data = _smf(480, _chunk(b"MTrk", b"\x00\xf0\x04abc"))
        self._assert_error(data, "system exclusive")

    def test_truncated_delta_time(self):
        data = _smf(480, _chunk(b"MTrk", b"\x80\x80"))
        self._assert_error(data, "delta time")

    def test_error_reports_the_failing_track(self):
        good = _track([_note(10), _end_of_track()])
        bad = _chunk(b"MTrk", b"\x00\x90\x3c")
        data = _smf(480, good, bad, format_=1)
        try:
            SMF(BytesIO(data))
        except SMFError as e:
            self.assertTrue("Track 2" in str(e), str(e))
        else:
            self.fail("SMFError not raised")

    def test_zero_time_division(self):
        data = _smf(0, _track([_end_of_track()]))
        self.failUnlessRaises(SMFError, SMF, BytesIO(data))

    def test_unsupported_format(self):
        data = _header(2, 1, 480) + _track([_end_of_track()])
        self.failUnlessRaises(SMFError, SMF, BytesIO(data))

    def test_truncated_header_chunk(self):
        self.failUnlessRaises(SMFError, SMF, BytesIO(b"MThd\x00\x00"))

    def test_truncated_track_chunk(self):
        data = _header(0, 1, 480) + b"MTrk\x00\x00\x00\x10abc"
        self.failUnlessRaises(SMFError, SMF, BytesIO(data))

    def test_not_a_midi_file(self):
        self.failUnlessRaises(SMFError, SMF, BytesIO(b"XXXXxxxx"))
