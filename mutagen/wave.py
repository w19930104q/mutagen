# Copyright (C) 2017  Borewit
# Copyright (C) 2019-2020  Philipp Wolfer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

"""Microsoft WAVE/RIFF audio file/stream information and tags."""

import sys
import struct

from mutagen import StreamInfo, FileType
from mutagen._tags import Tags

from mutagen.id3 import ID3
from mutagen._riff import RiffFile
from mutagen._iff import (
    assert_valid_chunk_id,
    error as _IffError,
    InvalidChunk,
)
from mutagen.id3._util import ID3NoHeaderError, error as ID3Error
from mutagen._util import (
    DictMixin,
    convert_error,
    endswith,
    loadfile,
    reraise,
)

__all__ = ["WAVE", "Open", "WaveListInfo", "delete"]


class error(_IffError):
    """WAVE stream parsing errors."""


class _WaveFile(RiffFile):
    """Representation of a RIFF/WAVE file"""

    def __init__(self, fileobj):
        RiffFile.__init__(self, fileobj)

        if self.file_type != u'WAVE':
            raise error("Expected RIFF/WAVE.")

        # Normalize ID3v2-tag-chunk to lowercase
        if u'ID3' in self:
            self[u'ID3'].id = u'id3'

    def find_info_list(self):
        """Returns the LIST/INFO chunk of the file or None if it does not
        exist.

        A RIFF file may contain more than one LIST chunk, potentially with
        different list type identifiers (e.g. INFO, adtl), so all LIST chunks
        are searched instead of looking up the first one by ID.
        """

        for chunk in self.root.subchunks():
            if chunk.id == u'LIST' and chunk.name == u'INFO':
                return chunk
        return None


class WaveStreamInfo(StreamInfo):
    """WaveStreamInfo()

    Microsoft WAVE file information.

    Information is parsed from the 'fmt' & 'data'chunk of the RIFF/WAVE file

    Attributes:
        length (`float`): audio length, in seconds
        bitrate (`int`): audio bitrate, in bits per second
        channels (`int`): The number of audio channels
        sample_rate (`int`): audio sample rate, in Hz
        bits_per_sample (`int`): The audio sample size
    """

    length = 0.0
    bitrate = 0
    channels = 0
    sample_rate = 0
    bits_per_sample = 0

    SIZE = 16

    @convert_error(IOError, error)
    def __init__(self, fileobj):
        """Raises error"""

        wave_file = _WaveFile(fileobj)
        try:
            format_chunk = wave_file[u'fmt']
        except KeyError as e:
            raise error(str(e))

        data = format_chunk.read()
        if len(data) < 16:
            raise InvalidChunk()

        # RIFF: http://soundfile.sapp.org/doc/WaveFormat/
        #  Python struct.unpack:
        #    https://docs.python.org/2/library/struct.html#byte-order-size-and-alignment
        info = struct.unpack('<HHLLHH', data[:self.SIZE])
        self.audio_format, self.channels, self.sample_rate, byte_rate, \
            block_align, self.bits_per_sample = info
        self.bitrate = self.channels * self.bits_per_sample * self.sample_rate

        # Calculate duration
        self._number_of_samples = 0
        if block_align > 0:
            try:
                data_chunk = wave_file[u'data']
                self._number_of_samples = data_chunk.data_size / block_align
            except KeyError:
                pass

        if self.sample_rate > 0:
            self.length = self._number_of_samples / self.sample_rate

    def pprint(self):
        return u"%d channel RIFF @ %d bps, %s Hz, %.2f seconds" % (
            self.channels, self.bitrate, self.sample_rate, self.length)


class _WaveID3(ID3):
    """A Wave file with ID3v2 tags"""

    def _pre_load_header(self, fileobj):
        try:
            fileobj.seek(_WaveFile(fileobj)[u'id3'].data_offset)
        except (InvalidChunk, KeyError):
            raise ID3NoHeaderError("No ID3 chunk")

    @convert_error(IOError, error)
    @loadfile(writable=True)
    def save(self, filething, v1=1, v2_version=4, v23_sep='/', padding=None):
        """Save ID3v2 data to the Wave/RIFF file"""

        fileobj = filething.fileobj
        wave_file = _WaveFile(fileobj)

        if u'id3' not in wave_file:
            wave_file.insert_chunk(u'id3')

        chunk = wave_file[u'id3']

        try:
            data = self._prepare_data(
                fileobj, chunk.data_offset, chunk.data_size, v2_version,
                v23_sep, padding)
        except ID3Error as e:
            reraise(error, e, sys.exc_info()[2])

        chunk.resize(len(data))
        chunk.write(data)

    def delete(self, filething):
        """Completely removes the ID3 chunk from the RIFF/WAVE file"""

        delete(filething)
        self.clear()


class WaveListInfo(Tags, DictMixin):
    """WaveListInfo(filething=None)

    The ``LIST/INFO`` tags of a RIFF/WAVE file.

    The tags are exposed as a dictionary with the RIFF field identifiers
    (e.g. ``INAM``, ``IART``, ``IPRD``) as keys and strings as values.

    ::

        wav = WAVE("example.wav")
        wav.list_info["INAM"] = "A title"
        wav.list_info.save()

    A WAVE file can carry LIST/INFO tags and an ID3 tag at the same time.
    The two tagging formats are handled independently of each other, so
    saving the LIST/INFO tags never modifies the ID3 tag and vice versa.
    """

    filename = None

    def __init__(self, filething=None):
        self._tags = {}
        if filething is not None:
            self.load(filething)

    @staticmethod
    def _decode(data):
        """Decode the raw bytes of an INFO field into a string."""

        text = bytes(data).rstrip(b'\x00')
        try:
            return text.decode('windows-1252')
        except UnicodeDecodeError:
            # windows-1252 normally maps every byte, but keep a lossless
            # fallback for files containing arbitrary data.
            return text.decode('latin-1')

    @staticmethod
    def _encode(value):
        """Encode a string into the raw bytes of an INFO field.

        The resulting data is always NUL terminated as required by the
        RIFF specification and gets a padding byte appended if the total
        length is odd (the padding is handled by the chunk write itself).
        """

        if not isinstance(value, str):
            raise TypeError("INFO values must be strings")
        try:
            data = value.encode('windows-1252')
        except UnicodeEncodeError:
            data = value.encode('latin-1')
        return data + b'\x00'

    @convert_error(IOError, error)
    @loadfile()
    def load(self, filething):
        """Load all LIST/INFO tags from the file."""

        wave_file = _WaveFile(filething.fileobj)
        info_list = wave_file.find_info_list()

        tags = {}
        if info_list is not None:
            for chunk in info_list.subchunks():
                # If a field identifier appears more than once only the
                # first field is exposed; the duplicates are discarded
                # when saving.
                if chunk.id not in tags:
                    tags[chunk.id] = self._decode(chunk.read())

        self._tags = tags

    @convert_error(IOError, error)
    @loadfile(writable=True)
    def save(self, filething=None):
        """Save the LIST/INFO tags to the RIFF/WAVE file.

        Only INFO fields that were actually changed are rewritten. The
        audio data, the ID3 tag and all other chunks are never touched, and
        INFO fields that remain unchanged keep their exact original byte
        representation (including their padding byte).
        """

        fileobj = filething.fileobj
        wave_file = _WaveFile(fileobj)
        info_list = wave_file.find_info_list()

        new_tags = self._tags

        if not new_tags:
            if info_list is not None:
                info_list.delete()
            self._tags = {}
            return

        if info_list is None:
            info_list = wave_file.root.insert_chunk(
                u'LIST', b'INFO')
            existing = {}
        else:
            existing = {}
            for chunk in info_list.subchunks():
                existing.setdefault(chunk.id, []).append(chunk)

        # Remove fields that have been deleted from the mapping. Duplicate
        # fields with the same identifier are removed as well.
        for field_id, chunks in list(existing.items()):
            if field_id not in new_tags:
                for chunk in reversed(chunks):
                    chunk.delete()
                del existing[field_id]

        for field_id, value in new_tags.items():
            assert_valid_chunk_id(field_id)
            data = self._encode(value)
            chunks = existing.get(field_id)
            if chunks:
                # Keep the first field, drop any duplicate fields with the
                # same identifier.
                chunk, duplicates = chunks[0], chunks[1:]
                for duplicate in reversed(duplicates):
                    duplicate.delete()
                # Rewrite the field only if its content actually changed,
                # this keeps the original bytes (incl. padding) untouched.
                if chunk.read() != data:
                    chunk.resize(len(data))
                    chunk.write(data)
            else:
                info_list.insert_chunk(field_id, data)

        fileobj.flush()

    @convert_error(IOError, error)
    @loadfile(writable=True)
    def delete(self, filething=None):
        """Completely removes the LIST/INFO chunk from the RIFF/WAVE file"""

        wave_file = _WaveFile(filething.fileobj)
        info_list = wave_file.find_info_list()
        if info_list is not None:
            info_list.delete()
        self._tags = {}

    def __getitem__(self, key):
        return self._tags[key]

    def __setitem__(self, key, value):
        assert_valid_chunk_id(key)
        if not isinstance(value, str):
            raise TypeError("INFO values must be strings")
        self._tags[key] = value

    def __delitem__(self, key):
        del self._tags[key]

    def __iter__(self):
        return iter(self._tags)

    def __len__(self):
        return len(self._tags)

    def keys(self):
        return list(self._tags.keys())

    def pprint(self):
        return u"\n".join(u"%s=%s" % (key, self._tags[key])
                          for key in self._tags)


@convert_error(IOError, error)
@loadfile(method=False, writable=True)
def delete(filething):
    """Completely removes the ID3 chunk from the RIFF/WAVE file"""

    try:
        _WaveFile(filething.fileobj).delete_chunk(u'id3')
    except KeyError:
        pass


class WAVE(FileType):
    """WAVE(filething)

    A Waveform Audio File Format
    (WAVE, or more commonly known as WAV due to its filename extension)

    Arguments:
        filething (filething)

    Attributes:
        tags (`mutagen.id3.ID3`): the ID3v2 tag or `None` if the file has
            no ID3 tag
        list_info (`WaveListInfo`): the tags stored in the RIFF
            ``LIST/INFO`` chunk (always present, possibly empty)
        info (`WaveStreamInfo`)
    """

    _mimes = ["audio/wav", "audio/wave"]

    list_info = None

    @staticmethod
    def score(filename, fileobj, header):
        filename = filename.lower()

        riff_wave = header.startswith(b"RIFF") and header[8:12] == b"WAVE"
        return (2 * riff_wave
                + endswith(filename, b".wav") + endswith(filename, b".wave"))

    def add_tags(self):
        """Add an empty ID3 tag to the file."""
        if self.tags is None:
            self.tags = _WaveID3()
        else:
            raise error("an ID3 tag already exists")

    def add_list_info(self):
        """Ensure empty LIST/INFO tags are available for editing.

        The :attr:`list_info` attribute is always present, so this is
        mainly useful for symmetry with :meth:`add_tags`. The tags are not
        written to the file until :meth:`WaveListInfo.save` or
        :meth:`save` is called.
        """
        if self.list_info is None:
            self.list_info = WaveListInfo()
        else:
            raise error("LIST/INFO tags already exist")

    @convert_error(IOError, error)
    @loadfile()
    def load(self, filething, **kwargs):
        """Load stream and tag information from a file."""

        fileobj = filething.fileobj
        self.info = WaveStreamInfo(fileobj)
        fileobj.seek(0, 0)

        try:
            self.tags = _WaveID3(fileobj, **kwargs)
        except ID3NoHeaderError:
            self.tags = None
        except ID3Error as e:
            raise error(e)
        else:
            self.tags.filename = self.filename

        fileobj.seek(0, 0)
        self.list_info = WaveListInfo(fileobj)
        self.list_info.filename = self.filename

    @loadfile(writable=True)
    def save(self, filething=None, **kwargs):
        """Save the ID3 and the LIST/INFO tags to the file.

        Keyword arguments are forwarded to the ID3 tag saving code.
        """

        if self.tags is not None:
            self.tags.save(filething, **kwargs)
        if self.list_info is not None:
            self.list_info.save(filething)

    @loadfile(writable=True)
    def delete(self, filething=None):
        """Remove the ID3 tag and the LIST/INFO tags from the file."""

        if self.tags is not None:
            self.tags.delete(filething)
            self.tags = None
        if self.list_info is not None:
            self.list_info.delete(filething)
            self.list_info = None


Open = WAVE
