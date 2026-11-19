# Copyright 2015 Christoph Reiter
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

"""Standard MIDI File (SMF)"""

import struct
from typing import List, Tuple

from mutagen import StreamInfo, MutagenError
from mutagen._file import FileType
from mutagen._util import loadfile, endswith


class SMFError(MutagenError):
    pass


# event types used inside the event tuples
TEMPO, MIDI = range(2)

# Standard MIDI File SMPTE time division: the upper byte of the division
# stores the negative of the frame rate (24, 25, 29.97 or 30 fps).
_SMPTE_FRAME_RATES = {
    0xE8: 24.0,
    0xE7: 25.0,
    0xE3: 29.97,
    0xE2: 30.0,
}


def _var_int(data: bytearray, offset: int = 0) -> Tuple[int, int]:
    val = 0
    while 1:
        try:
            x = data[offset]
        except IndexError:
            raise SMFError("Not enough data")
        offset += 1
        val = (val << 7) + (x & 0x7F)
        if not (x & 0x80):
            return val, offset


def _read_track(chunk: bytes, tracknum: int) -> Tuple[
        List[tuple], List[tuple], int]:
    """Returns a list of midi events, tempo change events and the total
    length of the track in ticks

    Every event is stored as ``(tick, type, data)``: the absolute tick at
    which it occurs, either :data:`MIDI` (data is the event's delta time)
    or :data:`TEMPO` (data is the microseconds per quarter note), and the
    delta time of the event. The total length includes the delta times of
    all events, even trailing meta events such as the end-of-track marker.

    Raises :class:`SMFError` if the track data is truncated or contains an
    unknown event; the error message includes the track number and the
    offset inside the track so it can be located.
    """

    def error(message: str, offset: int) -> SMFError:
        return SMFError(
            "Track %d, offset %d: %s" % (tracknum + 1, offset, message))

    events = []
    tempos = []

    chunk = bytearray(chunk)
    deltasum = 0
    status = 0
    off = 0
    while off < len(chunk):
        event_off = off
        try:
            delta, off = _var_int(chunk, off)
        except SMFError:
            raise error("truncated delta time", off)
        deltasum += delta
        try:
            event_type = chunk[off]
        except IndexError:
            raise error("truncated event", off)
        off += 1
        if event_type == 0xFF:
            # meta event
            try:
                meta_type = chunk[off]
            except IndexError:
                raise error("truncated meta event", off)
            off += 1
            try:
                num, off = _var_int(chunk, off)
            except SMFError:
                raise error("truncated meta event length", off)
            if off + num > len(chunk):
                raise error("truncated meta event data", off)
            if meta_type == 0x51:
                # set tempo: 3 bytes microseconds per quarter note
                data = chunk[off:off + num]
                if len(data) != 3:
                    raise error("tempo event needs 3 data bytes, got %d"
                                % len(data), event_off)
                tempo = struct.unpack(">I", b"\x00" + bytes(data))[0]
                if tempo == 0:
                    raise error("tempo of zero microseconds per quarter note",
                                event_off)
                tempos.append((deltasum, TEMPO, tempo))
            # Time signature (0x58) and all other meta events only carry
            # notation information; the tempo map above is all that matters
            # for the duration, so just skip the payload.
            off += num
        elif event_type in (0xF0, 0xF7):
            # system exclusive event
            try:
                val, off = _var_int(chunk, off)
            except SMFError:
                raise error("truncated system exclusive length", off)
            if off + val > len(chunk):
                raise error("truncated system exclusive event", off)
            off += val
        else:
            if event_type < 0x80:
                # running status: reuse the status byte of the previous
                # MIDI event; the byte we just read is the first data byte
                if status == 0:
                    raise error(
                        "running status without a previous MIDI event",
                        event_off)
                # off points right after the first data byte; matching the
                # explicit status path below leaves one more byte to read
                off += 1
                event_type = status
            elif event_type < 0xF0:
                off += 2
                status = event_type
            else:
                raise error("invalid event 0x%02X" % event_type, event_off)

            # program change and channel pressure carry one data byte
            # instead of two
            if event_type >> 4 in (0xD, 0xC):
                off -= 1
            if off > len(chunk):
                raise error("truncated MIDI event", event_off)

            events.append((deltasum, MIDI, delta))

    return events, tempos, deltasum


def _read_midi_length(fileobj) -> float:
    """Returns the duration in seconds. Can raise all kind of errors..."""

    def read_chunk():
        info = fileobj.read(8)
        if len(info) != 8:
            raise SMFError("truncated chunk header")
        chunklen = struct.unpack(">I", info[4:])[0]
        data = fileobj.read(chunklen)
        if len(data) != chunklen:
            raise SMFError("truncated chunk data")
        return info[:4], data

    identifier, chunk = read_chunk()
    if identifier != b"MThd":
        raise SMFError("Not a MIDI file")

    if len(chunk) != 6:
        raise SMFError("truncated MIDI header")

    format_, ntracks, tickdiv = struct.unpack(">HHH", chunk)
    if format_ > 1:
        raise SMFError("Not supported format %d" % format_)

    if tickdiv == 0:
        raise SMFError("zero time division")

    if tickdiv >> 15:
        # SMPTE time division: the upper byte is the negative of the
        # frame rate and the lower byte gives the ticks (subframes) per
        # frame, so every tick takes 1 / (frame rate * ticks per frame)
        # seconds and tempo events have no effect on real time.
        fps_code = (tickdiv >> 8) & 0xFF
        if fps_code not in _SMPTE_FRAME_RATES:
            raise SMFError("Unknown SMPTE frame rate code 0x%02X" % fps_code)
        ticks_per_frame = tickdiv & 0xFF
        if ticks_per_frame == 0:
            raise SMFError("zero SMPTE ticks per frame")
        seconds_per_tick = 1.0 / (
            _SMPTE_FRAME_RATES[fps_code] * ticks_per_frame)

        # every track advances in the shared SMPTE time; the song ends at
        # the latest tick reached by any track, including trailing meta
        # events such as the end-of-track marker
        end_tick = 0
        for tracknum in range(ntracks):
            identifier, chunk = read_chunk()
            if identifier != b"MTrk":
                continue
            dummy_events, dummy_tempos, track_tick = _read_track(
                chunk, tracknum)
            end_tick = max(end_tick, track_tick)

        return end_tick * seconds_per_tick

    # metric (ticks per quarter note) time division: real time depends on
    # the tempo map. Tempo changes are global, so merge the tempo events
    # of all tracks and walk the resulting timeline up to the tick of the
    # last MIDI event of the longest track.
    tracks = []
    tempos = []
    for tracknum in range(ntracks):
        identifier, chunk = read_chunk()
        if identifier != b"MTrk":
            continue
        track_events, track_tempos, dummy_track_tick = _read_track(
            chunk, tracknum)
        tracks.append(track_events)
        tempos.extend(track_tempos)

    # the duration ends at the last MIDI event in any track; a track made
    # only of meta events (e.g. a tempo track) contributes no duration
    end_tick = 0
    for track_events in tracks:
        if track_events:
            end_tick = max(end_tick, track_events[-1][0])

    tempos.sort()

    duration = 0.0
    current_tick = 0
    # the default tempo is 120 BPM, i.e. 500000 us per quarter note
    current_tempo = 500000
    for (tick, dummy_type, tempo) in tempos:
        if tick > end_tick:
            break
        duration += ((tick - current_tick) / float(tickdiv)) * current_tempo
        current_tick = tick
        current_tempo = tempo
    duration += ((end_tick - current_tick) / float(tickdiv)) * current_tempo
    duration /= 10 ** 6

    return duration


class SMFInfo(StreamInfo):
    """SMFInfo()

    Attributes:
        length (`float`): Length in seconds

    """

    def __init__(self, fileobj):
        """Raises SMFError"""

        self.length = _read_midi_length(fileobj)

    def pprint(self):
        return u"SMF, %.2f seconds" % self.length


class SMF(FileType):
    """SMF(filething)

    Standard MIDI File (SMF)

    Attributes:
        info (`SMFInfo`)
        tags: `None`
    """

    _mimes = ["audio/midi", "audio/x-midi"]

    @loadfile()
    def load(self, filething):
        try:
            self.info = SMFInfo(filething.fileobj)
        except SMFError:
            raise
        except (OSError, IndexError, struct.error) as e:
            # every truncated/corrupt file should surface as SMFError with
            # a locate-able message instead of a low level exception
            raise SMFError(e)

    def add_tags(self):
        raise SMFError("doesn't support tags")

    @staticmethod
    def score(filename, fileobj, header):
        filename = filename.lower()
        return header.startswith(b"MThd") and (
            endswith(filename, ".mid") or endswith(filename, ".midi"))


Open = SMF
error = SMFError

__all__ = ["SMF"]
