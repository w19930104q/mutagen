# -*- coding: utf-8 -*-
"""Full-sample and round-trip regression matrix.

This module pins down two invariants across *every* sample shipped in
``tests/data`` and every format mutagen supports, so that a change which
breaks one format fails loudly instead of silently:

1. Read-back consistency: every bundled sample can be opened through
   ``mutagen.File`` (or fails deterministically) and reading it twice
   yields identical results -- same detected type, same tags, same
   stream info.

2. Round-trip consistency: for every tag-capable format, writing a set
   of fields and reading the file back returns exactly those fields,
   preserves pre-existing tags, and leaves the stream info (duration)
   untouched.

The format matrix mirrors the default ``options`` list of
:func:`mutagen.File` (see ``mutagen/_file.py``); if a format is added
there it must be added here as well.
"""

import os

import pytest

from mutagen import File, MutagenError
from mutagen.aac import AAC, AACError
from mutagen.ac3 import AC3, AC3Error
from mutagen.aiff import AIFF
from mutagen.apev2 import APEv2File
from mutagen.asf import ASF
from mutagen.dsdiff import DSDIFF
from mutagen.dsf import DSF
from mutagen.flac import FLAC
from mutagen.id3 import ID3FileType, TIT2, TPE1, TALB, TCON, TXXX, COMM
from mutagen.monkeysaudio import MonkeysAudio
from mutagen.mp3 import MP3, EasyMP3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.easymp4 import EasyMP4
from mutagen.musepack import Musepack
from mutagen.oggflac import OggFLAC
from mutagen.oggopus import OggOpus
from mutagen.oggspeex import OggSpeex
from mutagen.oggtheora import OggTheora
from mutagen.oggvorbis import OggVorbis
from mutagen.optimfrog import OptimFROG
from mutagen.smf import SMF, SMFError
from mutagen.tak import TAK
from mutagen.trueaudio import TrueAudio, EasyTrueAudio
from mutagen.wave import WAVE
from mutagen.wavpack import WavPack

from tests import DATA_DIR, get_temp_copy


# Every file shipped in tests/data, no exceptions. New samples
# automatically join the read-back matrix.
SAMPLES = sorted(
    name for name in os.listdir(DATA_DIR)
    if os.path.isfile(os.path.join(DATA_DIR, name)))

assert SAMPLES, "no samples found, DATA_DIR wrong?"

# All types mutagen.File() can return, mirroring the default options in
# mutagen/_file.py::File. Keep in sync with that list.
ALL_FILE_TYPES = {
    MP3, TrueAudio, OggTheora, OggSpeex, OggVorbis, OggFLAC, FLAC, AIFF,
    APEv2File, MP4, ID3FileType, WavPack, Musepack, MonkeysAudio,
    OptimFROG, ASF, OggOpus, AAC, AC3, SMF, TAK, DSF, DSDIFF, WAVE,
}

# Formats without any tag support in mutagen; add_tags() must keep
# rejecting them so nobody silently writes tags nobody can read.
NON_TAGGABLE_TYPES = {AAC, AC3, SMF}

TAGGABLE_TYPES = ALL_FILE_TYPES - NON_TAGGABLE_TYPES

# Bare .id3 samples score as MP3 in File() and raise there; they are
# still valid ID3FileType input and covered explicitly.
ID3_ONLY_SAMPLES = ["id3v23_unsynch.id3", "id3v24_extended_header.id3",
                    "issue_21.id3"]


def _freeze(value):
    """Convert a tag/info value into a deterministic, comparable form."""

    if isinstance(value, (str, bytes, int, float, bool, type(None))):
        return value
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((str(k), _freeze(v)) for k, v in value.items()))
    if hasattr(value, "__dict__"):
        # e.g. DSF's FormatChunk nested in the info object
        return (type(value).__name__, _freeze(vars(value)))
    return repr(value)


def _tags_snapshot(tags):
    if tags is None:
        return None
    return tuple(sorted(
        (str(key), _freeze(value)) for key, value in tags.items()))


def _info_snapshot(info):
    return tuple(sorted(
        (key, _freeze(value)) for key, value in vars(info).items()))


def _read_outcome(path, easy):
    """Open a sample and return a comparable snapshot of the result."""

    try:
        audio = File(path, easy=easy)
    except Exception as exc:
        return ("error", type(exc).__name__)
    if audio is None:
        return ("none",)
    return ("ok", type(audio).__name__, _tags_snapshot(audio.tags),
            _info_snapshot(audio.info))


@pytest.mark.parametrize("name", SAMPLES)
def test_sample_readback_consistent(name):
    """Every bundled sample reads back identically on repeated opens,
    in both normal and easy mode (a deterministic error is also a
    consistent result)."""

    path = os.path.join(DATA_DIR, name)
    for easy in (False, True):
        first = _read_outcome(path, easy)
        second = _read_outcome(path, easy)
        assert first == second, \
            "%s (easy=%r): %r != %r" % (name, easy, first, second)


def test_sample_matrix_covers_all_formats():
    """The bundled samples exercise every format mutagen.File() knows."""

    detected = set()
    for name in SAMPLES:
        try:
            audio = File(os.path.join(DATA_DIR, name))
        except MutagenError:
            continue
        if audio is not None:
            detected.add(type(audio))

    # Bare .id3 files are not auto-detected; open them directly.
    for name in ID3_ONLY_SAMPLES:
        audio = ID3FileType(os.path.join(DATA_DIR, name))
        assert audio.tags is not None
        detected.add(type(audio))

    missing = ALL_FILE_TYPES - detected
    unexpected = detected - ALL_FILE_TYPES
    assert not missing, "formats not covered by any sample: %r" % missing
    assert not unexpected, "File() returned unknown types: %r" % unexpected


def _run_roundtrip(filename, file_type, write_fields, check_fields,
                   easy=False, direct=False):
    """Copy a sample, write fields, save, re-read and verify.

    Also asserts that pre-existing tag keys survive the save and that
    the stream duration is not affected by tagging.

    ``direct`` opens the sample through the format class itself instead
    of mutagen.File() (needed for bare .id3 files, which File() cannot
    detect).
    """

    path = get_temp_copy(os.path.join(DATA_DIR, filename))

    def load(p):
        if direct:
            return file_type(p)
        return File(p, easy=easy)

    try:
        audio = load(path)
        assert type(audio) is file_type, \
            "%s detected as %r" % (filename, type(audio).__name__)
        length_before = audio.info.length
        preserved_keys = set(audio.tags.keys()) if audio.tags else set()
        if audio.tags is None:
            audio.add_tags()
        assert audio.tags is not None
        write_fields(audio)
        audio.save()

        again = load(path)
        assert type(again) is file_type
        check_fields(again)
        missing = preserved_keys - set(again.tags.keys())
        assert not missing, "save lost pre-existing keys: %r" % missing
        assert again.info.length == length_before
    finally:
        os.unlink(path)


# -- field writers / checkers per tag family ------------------------------

EASY_FIELDS = {
    "title": [u"Regression Tïtle"],
    "artist": [u"Regression Ärtist"],
    "album": [u"Regression Album"],
    "genre": [u"Regression Genre"],
    "date": [u"2026"],
}


def _write_easy(audio):
    for key, value in EASY_FIELDS.items():
        audio[key] = value


def _check_easy(audio):
    for key, value in EASY_FIELDS.items():
        assert list(audio[key]) == value, (key, audio.get(key))


VORBIS_FIELDS = {
    "title": [u"Regression Tïtle"],
    "artist": [u"Artist One", u"Artist Two"],
    "album": [u"Regression Album"],
    "regressionkey": [u"a", u"b", u"c"],
}


def _write_vorbis(audio):
    for key, value in VORBIS_FIELDS.items():
        audio.tags[key] = value


def _check_vorbis(audio):
    for key, value in VORBIS_FIELDS.items():
        assert list(audio.tags[key]) == value, (key, audio.tags.get(key))


APEV2_FIELDS = {
    "Title": u"Regression Tïtle",
    "Artist": u"Regression Ärtist",
    "Album": u"Regression Album",
}


def _write_apev2(audio):
    for key, value in APEV2_FIELDS.items():
        audio.tags[key] = value


def _check_apev2(audio):
    for key, value in APEV2_FIELDS.items():
        assert str(audio.tags[key]) == value, (key, audio.tags.get(key))


def _write_id3(audio):
    audio.tags.add(TIT2(encoding=3, text=[u"Regression Tïtle"]))
    audio.tags.add(TPE1(encoding=3, text=[u"Regression Ärtist"]))
    audio.tags.add(TALB(encoding=3, text=[u"Regression Album"]))
    audio.tags.add(TCON(encoding=3, text=[u"Regression Genre"]))
    audio.tags.add(TXXX(encoding=3, desc=u"REGKEY", text=[u"v1", u"v2"]))
    audio.tags.add(COMM(encoding=3, lang="eng", desc="",
                        text=[u"Regression Comment"]))


def _check_id3(audio):
    tags = audio.tags
    assert tags["TIT2"].text == [u"Regression Tïtle"]
    assert tags["TPE1"].text == [u"Regression Ärtist"]
    assert tags["TALB"].text == [u"Regression Album"]
    assert tags["TCON"].text == [u"Regression Genre"]
    assert tags["TXXX:REGKEY"].text == [u"v1", u"v2"]
    assert tags["COMM::eng"].text == [u"Regression Comment"]


MP4_COVER_DATA = b"\x89PNG\r\n\x1a\nregression-cover"


def _write_mp4(audio):
    tags = audio.tags
    tags["\xa9nam"] = [u"Regression Tïtle"]
    tags["\xa9ART"] = [u"Regression Ärtist"]
    tags["aART"] = [u"Regression AlbumArtist"]
    tags["\xa9alb"] = [u"Regression Album"]
    tags["\xa9day"] = [u"2026"]
    tags["trkn"] = [(3, 10)]
    tags["disk"] = [(1, 2)]
    tags["tmpo"] = [128]
    tags["covr"] = [MP4Cover(MP4_COVER_DATA,
                             imageformat=MP4Cover.FORMAT_PNG)]
    tags["----:com.apple.iTunes:REGKEY"] = [b"regression-blob"]


def _check_mp4(audio):
    tags = audio.tags
    assert tags["\xa9nam"] == [u"Regression Tïtle"]
    assert tags["\xa9ART"] == [u"Regression Ärtist"]
    assert tags["aART"] == [u"Regression AlbumArtist"]
    assert tags["\xa9alb"] == [u"Regression Album"]
    assert tags["\xa9day"] == [u"2026"]
    assert tags["trkn"] == [(3, 10)]
    assert tags["disk"] == [(1, 2)]
    assert tags["tmpo"] == [128]
    assert bytes(tags["covr"][0]) == MP4_COVER_DATA
    assert tags["covr"][0].imageformat == MP4Cover.FORMAT_PNG
    assert [bytes(v) for v in tags["----:com.apple.iTunes:REGKEY"]] == \
        [b"regression-blob"]


ASF_FIELDS = {
    "Title": [u"Regression Tïtle"],
    "Author": [u"Artist One", u"Artist Two"],
    "WM/AlbumTitle": [u"Regression Album"],
    "WM/Genre": [u"Regression Genre"],
    "WM/Year": [u"2026"],
}


def _write_asf(audio):
    for key, value in ASF_FIELDS.items():
        audio.tags[key] = value


def _check_asf(audio):
    for key, value in ASF_FIELDS.items():
        assert [str(v) for v in audio.tags[key]] == value, key


# -- the round-trip matrix -------------------------------------------------
# (case id, sample, expected type, easy mode, writer, checker)

ROUNDTRIP_CASES = [
    # ID3-based formats
    ("MP3", "silence-44-s.mp3", MP3, False, _write_id3, _check_id3),
    ("MP3-easy", "silence-44-s.mp3", EasyMP3, True,
     _write_easy, _check_easy),
    ("TrueAudio", "empty.tta", TrueAudio, False, _write_id3, _check_id3),
    ("TrueAudio-easy", "empty.tta", EasyTrueAudio, True,
     _write_easy, _check_easy),
    ("AIFF-notags", "8k-1ch-1s-silence.aif", AIFF, False,
     _write_id3, _check_id3),
    ("AIFF-with-id3", "with-id3.aif", AIFF, False, _write_id3, _check_id3),
    ("WAVE-notags", "silence-2s-PCM-16000-08-notags.wav", WAVE, False,
     _write_id3, _check_id3),
    ("WAVE-with-id3", "silence-2s-PCM-16000-08-ID3v23.wav", WAVE, False,
     _write_id3, _check_id3),
    ("DSF-without-id3", "without-id3.dsf", DSF, False,
     _write_id3, _check_id3),
    ("DSF-with-id3", "with-id3.dsf", DSF, False, _write_id3, _check_id3),
    ("DSDIFF", "2822400-1ch-0s-silence.dff", DSDIFF, False,
     _write_id3, _check_id3),
    ("ID3FileType", "id3v23_unsynch.id3", ID3FileType, False,
     _write_id3, _check_id3),
    # VorbisComment-based formats
    ("FLAC", "silence-44-s.flac", FLAC, False,
     _write_vorbis, _check_vorbis),
    ("OggVorbis", "empty.ogg", OggVorbis, False,
     _write_vorbis, _check_vorbis),
    ("OggOpus", "example.opus", OggOpus, False,
     _write_vorbis, _check_vorbis),
    ("OggFLAC", "empty.oggflac", OggFLAC, False,
     _write_vorbis, _check_vorbis),
    ("OggSpeex", "empty.spx", OggSpeex, False,
     _write_vorbis, _check_vorbis),
    ("OggTheora", "sample.oggtheora", OggTheora, False,
     _write_vorbis, _check_vorbis),
    # APEv2-based formats
    ("APEv2File", "oldtag.apev2", APEv2File, False,
     _write_apev2, _check_apev2),
    ("MonkeysAudio", "mac-396.ape", MonkeysAudio, False,
     _write_apev2, _check_apev2),
    ("Musepack", "sv8_header.mpc", Musepack, False,
     _write_apev2, _check_apev2),
    ("WavPack", "silence-44-s.wv", WavPack, False,
     _write_apev2, _check_apev2),
    ("TAK-notags", "silence-44-s.tak", TAK, False,
     _write_apev2, _check_apev2),
    ("TAK-with-tags", "has-tags.tak", TAK, False,
     _write_apev2, _check_apev2),
    ("OptimFROG-ofr", "empty.ofr", OptimFROG, False,
     _write_apev2, _check_apev2),
    ("OptimFROG-ofs", "empty.ofs", OptimFROG, False,
     _write_apev2, _check_apev2),
    # MP4
    ("MP4-notags", "no-tags.m4a", MP4, False, _write_mp4, _check_mp4),
    ("MP4-with-tags", "has-tags.m4a", MP4, False, _write_mp4, _check_mp4),
    ("MP4-3g2", "no-tags.3g2", MP4, False, _write_mp4, _check_mp4),
    ("MP4-easy", "no-tags.m4a", EasyMP4, True, _write_easy, _check_easy),
    # ASF
    ("ASF-1", "silence-1.wma", ASF, False, _write_asf, _check_asf),
    ("ASF-3", "silence-3.wma", ASF, False, _write_asf, _check_asf),
]


# Cases that must be opened through the format class directly because
# mutagen.File() cannot detect them (bare .id3 files score as MP3).
DIRECT_OPEN_IDS = {"ID3FileType"}


@pytest.mark.parametrize(
    "case_id,filename,file_type,easy,write_fields,check_fields",
    [case for case in ROUNDTRIP_CASES],
    ids=[case[0] for case in ROUNDTRIP_CASES])
def test_roundtrip(case_id, filename, file_type, easy, write_fields,
                   check_fields):
    """Written fields read back unchanged for every tag-capable format."""

    _run_roundtrip(filename, file_type, write_fields, check_fields,
                   easy=easy, direct=case_id in DIRECT_OPEN_IDS)


def test_roundtrip_matrix_covers_all_taggable_formats():
    """Every tag-capable format appears in the round-trip matrix."""

    covered = {case[2] for case in ROUNDTRIP_CASES}
    # Easy variants share the format with their base type.
    covered = covered | {MP3, TrueAudio, MP4}
    missing = TAGGABLE_TYPES - covered
    assert not missing, \
        "taggable formats missing from round-trip matrix: %r" % missing


@pytest.mark.parametrize("file_type,error,filename", [
    (AAC, AACError, "empty.aac"),
    (AC3, AC3Error, "silence-44-s.ac3"),
    (SMF, SMFError, "sample.mid"),
], ids=["AAC", "AC3", "SMF"])
def test_untaggable_formats_reject_add_tags(file_type, error, filename):
    """Formats without tag support must keep refusing add_tags()."""

    audio = file_type(os.path.join(DATA_DIR, filename))
    assert audio.tags is None
    with pytest.raises(error):
        audio.add_tags()
