
import os
import struct
from io import BytesIO

import mutagen

from mutagen.wave import WAVE, WaveListInfo
from mutagen._iff import InvalidChunk
from mutagen._riff import RiffFile
from tests import TestCase, DATA_DIR, get_temp_copy


class TWave(TestCase):
    def test_score_requires_wave_form(self):
        for form, filename in [(b"WEBP", "cover.webp"), (b"AVI ", "video.avi")]:
            header = b"RIFF\x08\x00\x00\x00" + form
            with self.subTest(form=form):
                self.assertEqual(WAVE.score(filename, BytesIO(header), header), 0)
                self.assertIsNone(mutagen.File(BytesIO(header)))

    def test_score_wave_header_and_extensions(self):
        header = b"RIFF\x08\x00\x00\x00WAVE"
        self.assertEqual(WAVE.score("audio", BytesIO(header), header), 2)
        for filename in ("audio.wav", "audio.WAVE"):
            with self.subTest(filename=filename):
                self.assertEqual(WAVE.score(filename, BytesIO(header), header), 3)
                self.assertEqual(WAVE.score(filename, BytesIO(), b""), 1)
        for header in (b"", b"RIFF", b"RIFF\x08\x00\x00\x00WA",
                       b"xxxx\x00\x00\x00\x00WAVE"):
            with self.subTest(header=header):
                self.assertEqual(WAVE.score("audio", BytesIO(header), header), 0)

    def setUp(self):
        fn_wav_pcm_2s_16000_08_id3v23 = \
            os.path.join(DATA_DIR, "silence-2s-PCM-16000-08-ID3v23.wav")
        self.wav_pcm_2s_16000_08_ID3v23 = \
            WAVE(fn_wav_pcm_2s_16000_08_id3v23)

        self.tmp_fn_pcm_2s_16000_08_ID3v23 = \
            get_temp_copy(fn_wav_pcm_2s_16000_08_id3v23)
        self.tmp_wav_pcm_2s_16000_08_ID3v23 = \
            WAVE(self.tmp_fn_pcm_2s_16000_08_ID3v23)

        self.fn_wav_pcm_2s_16000_08_notags = \
            os.path.join(DATA_DIR, "silence-2s-PCM-16000-08-notags.wav")
        self.wav_pcm_2s_16000_08_notags = \
            WAVE(self.fn_wav_pcm_2s_16000_08_notags)

        self.tmp_fn_pcm_2s_16000_08_notag = \
            get_temp_copy(self.fn_wav_pcm_2s_16000_08_notags)
        self.tmp_wav_pcm_2s_16000_08_notag = \
            WAVE(self.tmp_fn_pcm_2s_16000_08_notag)

        fn_wav_pcm_2s_44100_16_id3v23 = \
            os.path.join(DATA_DIR, "silence-2s-PCM-44100-16-ID3v23.wav")
        self.wav_pcm_2s_44100_16_ID3v23 = WAVE(fn_wav_pcm_2s_44100_16_id3v23)

    def test_channels(self):
        self.failUnlessEqual(self.wav_pcm_2s_16000_08_ID3v23.info.channels, 2)
        self.failUnlessEqual(self.wav_pcm_2s_44100_16_ID3v23.info.channels, 2)

    def test_sample_rate(self):
        self.failUnlessEqual(self.wav_pcm_2s_16000_08_ID3v23.info.sample_rate,
                             16000)
        self.failUnlessEqual(self.wav_pcm_2s_44100_16_ID3v23.info.sample_rate,
                             44100)

    def test_number_of_samples(self):
        self.failUnlessEqual(self.wav_pcm_2s_16000_08_ID3v23.
                             info._number_of_samples, 32000)
        self.failUnlessEqual(self.wav_pcm_2s_44100_16_ID3v23.
                             info._number_of_samples, 88200)

    def test_bits_per_sample(self):
        self.failUnlessEqual(self.wav_pcm_2s_16000_08_ID3v23.
                             info.bits_per_sample, 8)
        self.failUnlessEqual(self.wav_pcm_2s_44100_16_ID3v23.
                             info.bits_per_sample, 16)

    def test_bitrate(self):
        self.failUnlessEqual(self.wav_pcm_2s_16000_08_ID3v23.
                             info.bitrate, 256000)
        self.failUnlessEqual(self.wav_pcm_2s_44100_16_ID3v23.
                             info.bitrate, 1411200)

    def test_length(self):
        self.failUnlessAlmostEqual(self.wav_pcm_2s_16000_08_ID3v23.info.length,
                                   2.0, 2)
        self.failUnlessAlmostEqual(self.wav_pcm_2s_44100_16_ID3v23.info.length,
                                   2.0, 2)

    def test_not_my_file(self):
        self.failUnlessRaises(
            InvalidChunk, WAVE, os.path.join(DATA_DIR, "empty.ogg"))

    def test_pprint(self):
        self.wav_pcm_2s_44100_16_ID3v23.pprint()

    def test_mime(self):
        self.failUnless("audio/wav" in self.wav_pcm_2s_44100_16_ID3v23.mime)
        self.failUnless("audio/wave" in self.wav_pcm_2s_44100_16_ID3v23.mime)

    def test_id3_tags(self):
        id3 = self.wav_pcm_2s_44100_16_ID3v23.tags
        self.assertEquals(id3["TALB"], "Quod Libet Test Data")
        self.assertEquals(id3["TCON"], "Silence")
        self.assertEquals(id3["TIT2"], "Silence")
        self.assertEquals(id3["TPE1"], ["piman / jzig"])

    def test_id3_tags_uppercase_chunk(self):
        id3 = self.wav_pcm_2s_16000_08_ID3v23
        self.assertEquals(id3["TALB"], "Quod Libet Test Data")
        self.assertEquals(id3["TCON"], "Silence")
        self.assertEquals(id3["TIT2"], "Silence")
        self.assertEquals(id3["TPE1"], ["piman / jzig"])

    def test_delete(self):
        self.tmp_wav_pcm_2s_16000_08_ID3v23.delete()

        self.failIf(self.tmp_wav_pcm_2s_16000_08_ID3v23.tags)
        self.failUnless(WAVE(self.tmp_fn_pcm_2s_16000_08_ID3v23).tags is None)

    def test_save_no_tags(self):
        self.tmp_wav_pcm_2s_16000_08_ID3v23.tags = None
        self.tmp_wav_pcm_2s_16000_08_ID3v23.save()
        self.assertTrue(self.tmp_wav_pcm_2s_16000_08_ID3v23.tags is None)

    def test_add_tags_already_there(self):
        self.failUnless(self.tmp_wav_pcm_2s_16000_08_ID3v23.tags)
        self.failUnlessRaises(Exception,
                              self.tmp_wav_pcm_2s_16000_08_ID3v23.add_tags)

    def test_roundtrip(self):
        self.failUnlessEqual(self.tmp_wav_pcm_2s_16000_08_ID3v23["TIT2"],
                             ["Silence"])
        self.tmp_wav_pcm_2s_16000_08_ID3v23.save()
        new = WAVE(self.tmp_wav_pcm_2s_16000_08_ID3v23.filename)
        self.failUnlessEqual(new["TIT2"], ["Silence"])

    def test_save_tags(self):
        from mutagen.id3 import TIT1
        tags = self.tmp_wav_pcm_2s_16000_08_ID3v23.tags
        tags.add(TIT1(encoding=3, text="foobar"))
        tags.save()

        new = WAVE(self.tmp_wav_pcm_2s_16000_08_ID3v23.filename)
        self.failUnlessEqual(new["TIT1"], ["foobar"])

    """" Simulate the way Picard writes and update tags """
    def test_picard_lifecycle(self):
        path_tmp_wav_file = \
            get_temp_copy(self.fn_wav_pcm_2s_16000_08_notags)
        from mutagen.id3 import ID3
        wav = WAVE(path_tmp_wav_file)
        id3 = wav.tags
        """" Picard WaveFile._get_tags: """
        self.assertIsNone(id3, "Ensure ID3-tag-header does not exist")
        """" Picard WaveFile._get_tags: initialize tags """
        wav.add_tags()
        id3 = wav.tags
        self.assertIsInstance(id3, ID3)
        """ ID3v2.3 separator """
        separator = '/'
        """ Initialize Picard like metadata tags """
        self.__init_id3_tags(id3, major=3)
        """ Write the Picard like metadata to the empty WAVE-file """
        id3.save(path_tmp_wav_file, v23_sep=separator)
        """ Tags (metadata) have been added; now load the file again """
        wav = WAVE(path_tmp_wav_file)
        id3 = wav.tags
        self.assertIsInstance(id3, ID3)
        self.assertEquals(id3["TRCK"], "1/10")
        self.assertEquals(id3["TPOS"], "1/1")
        self.assertEquals(id3["TXXX:MusicBrainz Release Group Id"],
                          "e00305af-1c72-469b-9a7c-6dc665ca9adc")
        self.assertEquals(id3["TXXX:MusicBrainz Album Artist Id"], [
                          "3fe817fc-966e-4ece-b00a-76be43e7e73c",
                          "984f8239-8fe1-4683-9c54-10ffb14439e9"])
        self.assertEquals(id3["TXXX:CATALOGNUMBER"], ["PRAR931391"])
        self.assertEquals(id3["TSRC"], ["NLB931100460", "USMH51100098"])

    @staticmethod
    def __init_id3_tags(id3, major=3):
        """
        Attributes:
            id3 ID3 Tag object
            major ID3 major version, e.g.: 3 for ID3v2.3
        """
        from mutagen.id3 import TRCK, TPOS, TXXX, TPUB, TALB, UFID, TPE2, \
            TSO2, TMED, TIT2, TPE1, TSRC, IPLS, TORY, TDAT, TYER
        id3.add(TRCK(encoding=major, text="1/10"))
        id3.add(TPOS(encoding=major, text="1/1"))
        id3.add(TXXX(encoding=major, desc="MusicBrainz Release Group Id",
                     text="e00305af-1c72-469b-9a7c-6dc665ca9adc"))
        id3.add(TXXX(encoding=major, desc="originalyear", text="2011"))
        id3.add(TXXX(encoding=major, desc="MusicBrainz Album Type",
                     text="album"))
        id3.add(TXXX(encoding=major, desc="MusicBrainz Album Id",
                     text="e7050302-74e6-42e4-aba0-09efd5d431d8"))
        id3.add(TPUB(encoding=major, text="J&R Adventures"))
        id3.add(TXXX(encoding=major, desc="CATALOGNUMBER", text="PRAR931391"))
        id3.add(TALB(encoding=major, text="Don\'t Explain"))
        id3.add(TXXX(encoding=major, desc="MusicBrainz Album Status",
                     text="official"))
        id3.add(TXXX(encoding=major, desc="SCRIPT", text="Latn"))
        id3.add(TXXX(encoding=major, desc="MusicBrainz Album Release Country",
                     text="US"))
        id3.add(TXXX(encoding=major, desc="BARCODE", text="804879313915"))
        id3.add(TXXX(encoding=major, desc="MusicBrainz Album Artist Id",
                     text=[
                        "3fe817fc-966e-4ece-b00a-76be43e7e73c",
                        "984f8239-8fe1-4683-9c54-10ffb14439e9"]))
        id3.add(TPE2(encoding=major, text="Beth Hart & Joe Bonamassa"))
        id3.add(TSO2(encoding=major, text="Hart, Beth & Bonamassa, Joe"))
        id3.add(TXXX(encoding=major, desc="ASIN", text="B005NPEUB2"))
        id3.add(TMED(encoding=major, text="CD"))
        id3.add(UFID(encoding=major, owner="http://musicbrainz.org",
                     data=b"f151cb94-c909-46a8-ad99-fb77391abfb8"))
        id3.add(TIT2(encoding=major, text="Sinner's Prayer"))
        id3.add(TXXX(encoding=major, desc="MusicBrainz Artist Id",
                     text=[
                        "3fe817fc-966e-4ece-b00a-76be43e7e73c",
                        "984f8239-8fe1-4683-9c54-10ffb14439e9"]))
        id3.add(TPE1(encoding=major, text=["Beth Hart & Joe Bonamassa"]))
        id3.add(TXXX(encoding=major, desc="Artists",
                     text=["Beth Hart", "Joe Bonamassa"]))
        id3.add(TSRC(encoding=major, text=["NLB931100460", "USMH51100098"]))
        id3.add(TXXX(encoding=major, desc="MusicBrainz Release Track Id",
                     text="d062f484-253c-374b-85f7-89aab45551c7"))
        id3.add(IPLS(encoding=major, people=[
            ["engineer", "James McCullagh"],
            ["engineer", "Jared Kvitka"],
            ["arranger", "Jeff Bova"],
            ["producer", "Roy Weisman"],
            ["piano", "Beth Hart"],
            ["guitar", "Blondie Chaplin"],
            ["guitar", "Joe Bonamassa"],
            ["percussion", "Anton Fig"],
            ["drums", "Anton Fig"],
            ["keyboard", "Arlan Schierbaum"],
            ["bass guitar", "Carmine Rojas"],
            ["orchestra", "The Bovaland Orchestra"],
            ["vocals", "Beth Hart"],
            ["vocals", "Joe Bonamassa"]])),
        id3.add(TORY(encoding=major, text="2011"))
        id3.add(TYER(encoding=major, text="2011"))
        id3.add(TDAT(encoding=major, text="2709"))


class TWaveListInfo(TestCase):

    INFO_FIELDS = {
        u"IPRD": u"Quod Libet Test Data",
        u"IART": u"piman, jzig",
        u"IGNR": u"Silence",
        u"INAM": u"Silence",
        u"ICRD": u"2004",
    }

    def setUp(self):
        self.fn_with_tags = os.path.join(
            DATA_DIR, "silence-2s-PCM-44100-16-ID3v23.wav")
        self.fn_no_tags = os.path.join(
            DATA_DIR, "silence-2s-PCM-16000-08-notags.wav")

        self.tmp_with_tags = get_temp_copy(self.fn_with_tags)
        self.wav_with_tags = WAVE(self.tmp_with_tags)

        self.tmp_no_tags = get_temp_copy(self.fn_no_tags)
        self.wav_no_tags = WAVE(self.tmp_no_tags)

    @staticmethod
    def _raw_chunks(path):
        riff = RiffFile(open(path, "rb"))
        chunks = {}
        with open(path, "rb") as fileobj:
            for chunk in riff.root.subchunks():
                fileobj.seek(chunk.offset)
                chunks.setdefault(chunk.id, []).append(
                    fileobj.read(chunk.size))
        return chunks

    @staticmethod
    def _audio_chunks(path):
        riff = RiffFile(open(path, "rb"))
        result = {}
        with open(path, "rb") as fileobj:
            for chunk_id in (u"fmt", u"data"):
                chunk = riff[chunk_id]
                fileobj.seek(chunk.offset)
                result[chunk_id] = fileobj.read(chunk.size)
        return result

    @staticmethod
    def _info_list(path):
        riff = RiffFile(open(path, "rb"))
        for chunk in riff.root.subchunks():
            if chunk.id == u"LIST" and chunk.name == u"INFO":
                return chunk
        return None

    @staticmethod
    def _raw_info_chunk(path):
        chunk = TWaveListInfo._info_list(path)
        if chunk is None:
            return None
        with open(path, "rb") as fileobj:
            fileobj.seek(chunk.offset)
            return fileobj.read(chunk.size)

    def test_list_info_always_present(self):
        self.assertIsInstance(self.wav_with_tags.list_info, WaveListInfo)
        self.assertIsInstance(self.wav_no_tags.list_info, WaveListInfo)
        self.assertEqual(len(self.wav_no_tags.list_info), 0)

    def test_read_existing_info_fields(self):
        list_info = self.wav_with_tags.list_info
        for key, value in self.INFO_FIELDS.items():
            self.assertEqual(list_info[key], value)
        # ITRK differs between the two test files, just make sure it reads
        self.assertIn(u"ITRK", list_info)
        self.assertEqual(
            set(list_info.keys()),
            {u"IPRD", u"IART", u"IGNR", u"INAM", u"ITRK", u"ICRD"})

    def test_dict_interface(self):
        list_info = self.wav_with_tags.list_info
        self.assertIn(u"INAM", list_info)
        self.assertNotIn(u"XXXX", list_info)
        self.assertEqual(list_info.get(u"XXXX", u"default"), u"default")
        self.assertEqual(len(list_info), 6)
        self.assertEqual(set(list_info.items()),
                         {(k, list_info[k]) for k in list_info})
        self.assertEqual(sorted(list_info.values()),
                         sorted(list_info._tags.values()))
        self.assertIn(u"INAM=Silence", list_info.pprint())

    def test_info_and_id3_coexist(self):
        self.assertIsNotNone(self.wav_with_tags.tags)
        self.assertEqual(self.wav_with_tags[u"TIT2"], [u"Silence"])
        self.assertEqual(self.wav_with_tags.list_info[u"INAM"], u"Silence")

    def test_noop_save_is_byte_identical(self):
        before = open(self.tmp_with_tags, "rb").read()
        self.wav_with_tags.list_info.save()
        self.assertEqual(open(self.tmp_with_tags, "rb").read(), before)

        # Saving through the WAVE object must leave the INFO chunk alone
        # (the ID3 tag itself may be re-encoded, that is existing behavior)
        info_before = self._raw_info_chunk(self.tmp_with_tags)
        self.wav_with_tags.save()
        self.assertEqual(self._raw_info_chunk(self.tmp_with_tags),
                         info_before)

    def test_modified_field_roundtrip_and_untouched_bytes(self):
        original_chunks = self._raw_chunks(self.tmp_with_tags)
        self.wav_with_tags.list_info[u"INAM"] = u"New Title"
        self.wav_with_tags.list_info.save()

        reloaded = WAVE(self.tmp_with_tags)
        self.assertEqual(reloaded.list_info[u"INAM"], u"New Title")
        self.assertEqual(reloaded.list_info[u"IART"], u"piman, jzig")

        new_chunks = self._raw_chunks(self.tmp_with_tags)
        # Audio data, fmt chunk and ID3 chunk are byte identical
        self.assertEqual(new_chunks[u"fmt"], original_chunks[u"fmt"])
        self.assertEqual(new_chunks[u"data"], original_chunks[u"data"])
        self.assertEqual(new_chunks[u"id3"], original_chunks[u"id3"])

        # Every unmodified INFO field keeps its exact on-disk bytes
        def subfield(raw, field_id):
            index = raw.index(field_id)
            size = struct.unpack("<I", raw[index + 4:index + 8])[0]
            return raw[index:index + 8 + size + (size % 2)]

        before = self._raw_info_chunk(self.fn_with_tags)
        after = self._raw_info_chunk(self.tmp_with_tags)
        for field_id in (b"IPRD", b"IART", b"IGNR", b"ITRK", b"ICRD"):
            self.assertEqual(subfield(before, field_id),
                             subfield(after, field_id))

    def test_read_modify_read_two_cycles(self):
        for cycle in range(2):
            wav = WAVE(self.tmp_with_tags)
            wav.list_info[u"INAM"] = u"Title %d" % cycle
            wav.list_info[u"ICMT"] = u"Comment %d" % cycle
            wav.list_info.pop(u"IGNR", None)
            wav.list_info.save()

        final = WAVE(self.tmp_with_tags)
        self.assertEqual(final.list_info[u"INAM"], u"Title 1")
        self.assertEqual(final.list_info[u"ICMT"], u"Comment 1")
        self.assertNotIn(u"IGNR", final.list_info)
        self.assertEqual(self._audio_chunks(self.tmp_with_tags),
                         self._audio_chunks(self.fn_with_tags))

    def test_add_field_to_existing_info(self):
        self.wav_with_tags.list_info[u"ICMT"] = u"a comment"
        self.wav_with_tags.list_info.save()

        reloaded = WAVE(self.tmp_with_tags)
        self.assertEqual(reloaded.list_info[u"ICMT"], u"a comment")
        self.assertEqual(reloaded.list_info[u"INAM"], u"Silence")

    def test_delete_field(self):
        del self.wav_with_tags.list_info[u"ICRD"]
        self.wav_with_tags.list_info.save()

        reloaded = WAVE(self.tmp_with_tags)
        self.assertNotIn(u"ICRD", reloaded.list_info)
        self.assertEqual(reloaded.list_info[u"INAM"], u"Silence")
        self.assertEqual(self._audio_chunks(self.tmp_with_tags),
                         self._audio_chunks(self.fn_with_tags))

    def test_odd_and_even_length_chunks(self):
        list_info = self.wav_no_tags.list_info
        list_info[u"INAM"] = u"AB"   # 2 chars + NUL = 3 bytes -> 1 pad byte
        list_info[u"IART"] = u"ABC"  # 3 chars + NUL = 4 bytes -> no padding
        list_info.save()

        info = self._info_list(self.tmp_no_tags)
        subchunks = {chunk.id: chunk for chunk in info.subchunks()}
        self.assertEqual(subchunks[u"INAM"].data_size, 3)
        self.assertEqual(subchunks[u"INAM"].padding(), 1)
        self.assertEqual(subchunks[u"IART"].data_size, 4)
        self.assertEqual(subchunks[u"IART"].padding(), 0)

        reloaded = WAVE(self.tmp_no_tags)
        self.assertEqual(reloaded.list_info[u"INAM"], u"AB")
        self.assertEqual(reloaded.list_info[u"IART"], u"ABC")

        # Resize the odd chunk to an even length and verify the padding
        # byte is removed correctly.
        reloaded.list_info[u"INAM"] = u"ABC"  # 3 chars + NUL = 4 bytes
        reloaded.list_info.save()

        info = self._info_list(self.tmp_no_tags)
        subchunks = {chunk.id: chunk for chunk in info.subchunks()}
        self.assertEqual(subchunks[u"INAM"].data_size, 4)
        self.assertEqual(subchunks[u"INAM"].padding(), 0)
        self.assertEqual(WAVE(self.tmp_no_tags).list_info[u"INAM"], u"ABC")

    def test_odd_length_chunk_deletion(self):
        list_info = self.wav_no_tags.list_info
        list_info[u"INAM"] = u"AB"  # odd data size, requires padding
        list_info[u"IART"] = u"Artist"
        list_info.save()
        del list_info[u"INAM"]
        list_info.save()

        reloaded = WAVE(self.tmp_no_tags)
        self.assertNotIn(u"INAM", reloaded.list_info)
        self.assertEqual(reloaded.list_info[u"IART"], u"Artist")
        self.assertEqual(self._audio_chunks(self.tmp_no_tags),
                         self._audio_chunks(self.fn_no_tags))

    def test_missing_info_block(self):
        self.assertIsNone(self._info_list(self.tmp_no_tags))

        # Saving an empty mapping must not create anything
        before = open(self.tmp_no_tags, "rb").read()
        self.wav_no_tags.list_info.save()
        self.assertEqual(open(self.tmp_no_tags, "rb").read(), before)

        # Creating the INFO block from scratch works
        self.wav_no_tags.list_info[u"INAM"] = u"Created"
        self.wav_no_tags.list_info.save()

        reloaded = WAVE(self.tmp_no_tags)
        self.assertEqual(reloaded.list_info[u"INAM"], u"Created")
        self.assertIsNone(reloaded.tags)
        self.assertEqual(self._audio_chunks(self.tmp_no_tags),
                         self._audio_chunks(self.fn_no_tags))

    def test_delete_info_chunk(self):
        self.assertIsNotNone(self._info_list(self.tmp_with_tags))
        self.wav_with_tags.list_info.delete()

        reloaded = WAVE(self.tmp_with_tags)
        self.assertEqual(len(reloaded.list_info), 0)
        self.assertIsNone(self._info_list(self.tmp_with_tags))
        # ID3 tag and audio data are untouched
        self.assertIsNotNone(reloaded.tags)
        self.assertEqual(self._audio_chunks(self.tmp_with_tags),
                         self._audio_chunks(self.fn_with_tags))

    def test_save_empty_mapping_removes_info_chunk(self):
        self.wav_with_tags.list_info.clear()
        self.wav_with_tags.list_info.save()
        self.assertIsNone(self._info_list(self.tmp_with_tags))
        self.assertIsNotNone(WAVE(self.tmp_with_tags).tags)

    def test_wave_delete_removes_info_and_id3(self):
        self.wav_with_tags.delete()
        reloaded = WAVE(self.tmp_with_tags)
        self.assertIsNone(reloaded.tags)
        self.assertEqual(len(reloaded.list_info), 0)
        self.assertIsNone(self._info_list(self.tmp_with_tags))
        self.assertEqual(self._audio_chunks(self.tmp_with_tags),
                         self._audio_chunks(self.fn_with_tags))

    def test_info_and_id3_do_not_interfere(self):
        from mutagen.id3 import TIT1

        wav = self.wav_with_tags
        wav.tags.add(TIT1(encoding=3, text=u"id3-only"))
        wav.list_info[u"INAM"] = u"info-only"
        wav.save()

        reloaded = WAVE(self.tmp_with_tags)
        self.assertEqual(reloaded.tags[u"TIT1"], [u"id3-only"])
        self.assertEqual(reloaded.list_info[u"INAM"], u"info-only")

        # An INFO save leaves the ID3 chunk bytes exactly as they were
        id3_before = self._raw_chunks(self.tmp_with_tags)[u"id3"]
        reloaded.list_info[u"IART"] = u"touched"
        reloaded.list_info.save()
        self.assertEqual(self._raw_chunks(self.tmp_with_tags)[u"id3"],
                         id3_before)

        # An ID3 save leaves the INFO chunk bytes exactly as they were
        info_before = self._raw_info_chunk(self.tmp_with_tags)
        WAVE(self.tmp_with_tags).tags.save()
        self.assertEqual(self._raw_info_chunk(self.tmp_with_tags),
                         info_before)

    def test_duplicate_field_identifiers(self):
        with open(self.tmp_no_tags, "rb+") as fileobj:
            riff = RiffFile(fileobj)
            info = riff.root.insert_chunk(u"LIST", b"INFO")
            info.insert_chunk(u"INAM", b"First\x00")
            info.insert_chunk(u"INAM", b"Second\x00")
            info.insert_chunk(u"IART", b"Artist\x00")

        wav = WAVE(self.tmp_no_tags)
        self.assertEqual(wav.list_info[u"INAM"], u"First")
        wav.list_info[u"INAM"] = u"Merged"
        wav.list_info.save()

        reloaded = WAVE(self.tmp_no_tags)
        self.assertEqual(reloaded.list_info[u"INAM"], u"Merged")
        self.assertEqual(reloaded.list_info[u"IART"], u"Artist")
        info = self._info_list(self.tmp_no_tags)
        identifiers = [chunk.id for chunk in info.subchunks()]
        self.assertEqual(identifiers.count(u"INAM"), 1)

    def test_multiple_list_chunks_non_info_ignored(self):
        with open(self.tmp_no_tags, "rb+") as fileobj:
            riff = RiffFile(fileobj)
            other = riff.root.insert_chunk(u"LIST", b"adtl")
            other.insert_chunk(u"labl", b"hello\x00")

        wav = WAVE(self.tmp_no_tags)
        self.assertEqual(len(wav.list_info), 0)

        # Saving empty tags must leave the adtl LIST chunk untouched
        before = open(self.tmp_no_tags, "rb").read()
        wav.list_info.save()
        self.assertEqual(open(self.tmp_no_tags, "rb").read(), before)

        # A newly created INFO chunk coexists with the adtl chunk
        wav.list_info[u"INAM"] = u"x"
        wav.list_info.save()
        riff = RiffFile(open(self.tmp_no_tags, "rb"))
        list_types = sorted(
            chunk.name for chunk in riff.root.subchunks()
            if chunk.id == u"LIST")
        self.assertEqual(list_types, [u"INFO", u"adtl"])
        self.assertEqual(WAVE(self.tmp_no_tags).list_info.keys(),
                         [u"INAM"])

    def test_standalone_constructor_and_fileobj(self):
        self.assertEqual(len(WaveListInfo()), 0)

        list_info = WaveListInfo(self.fn_with_tags)
        self.assertEqual(list_info[u"INAM"], u"Silence")

        list_info[u"INAM"] = u"ViaFileObj"
        with open(self.tmp_with_tags, "rb+") as fileobj:
            list_info.save(fileobj)
        with open(self.tmp_with_tags, "rb") as fileobj:
            self.assertEqual(WaveListInfo(fileobj)[u"INAM"], u"ViaFileObj")

    def test_value_and_key_validation(self):
        list_info = self.wav_no_tags.list_info
        with self.failUnlessRaises(TypeError):
            list_info[u"INAM"] = 123
        with self.failUnlessRaises(ValueError):
            list_info[u""] = u"value"

    def test_empty_string_value(self):
        self.wav_no_tags.list_info[u"INAM"] = u""
        self.wav_no_tags.list_info.save()
        reloaded = WAVE(self.tmp_no_tags)
        self.assertEqual(reloaded.list_info[u"INAM"], u"")
        # And grow the empty field again
        reloaded.list_info[u"INAM"] = u"not empty anymore"
        reloaded.list_info.save()
        self.assertEqual(
            WAVE(self.tmp_no_tags).list_info[u"INAM"],
            u"not empty anymore")
