
import os
from io import BytesIO

from mutagen.id3 import ID3, TIT1
from mutagen.aac import AAC, AACError

from tests import TestCase, DATA_DIR, get_temp_copy


class _BitWriter(object):

    def __init__(self):
        self._bits = []

    def write(self, value, count):
        for i in range(count - 1, -1, -1):
            self._bits.append((value >> i) & 1)

    def align(self):
        while len(self._bits) % 8:
            self._bits.append(0)

    def tobytes(self):
        self.align()
        out = bytearray()
        for i in range(0, len(self._bits), 8):
            byte = 0
            for bit in self._bits[i:i + 8]:
                byte = (byte << 1) | bit
            out.append(byte)
        return bytes(out)


def _pce(front_cpe=1, lfe=0):
    """id_syn_ele + program_config_element() for the given layout"""

    w = _BitWriter()
    w.write(0x5, 3)  # ID_PCE
    w.write(0, 4)  # element_instance_tag
    w.write(1, 2)  # object_type
    w.write(4, 4)  # sampling_frequency_index (44100)
    w.write(front_cpe, 4)  # num_front_channel_elements
    w.write(0, 4)  # num_side_channel_elements
    w.write(0, 4)  # num_back_channel_elements
    w.write(lfe, 2)  # num_lfe_channel_elements
    w.write(0, 3)  # num_assoc_data_elements
    w.write(0, 4)  # num_valid_cc_elements
    w.write(0, 1)  # mono_mixdown_present
    w.write(0, 1)  # stereo_mixdown_present
    w.write(0, 1)  # matrix_mixdown_idx_present
    for _ in range(front_cpe):
        w.write(1, 1)  # element_is_cpe
        w.write(0, 4)  # element_instance_tag
    for _ in range(lfe):
        w.write(0, 4)  # lfe_element_instance_tag
    w.align()
    w.write(0, 8)  # comment_field_bytes
    return w.tobytes()


def _adts_frame(payload, channel_config=2, protection_absent=1, nordbif=0,
                crc=b""):
    """One ADTS frame (44100 Hz, AAC LC) with the given payload.
    crc is inserted between header and payload if protection_absent == 0.
    """

    frame_length = 7 + len(crc) + len(payload)
    w = _BitWriter()
    w.write(0xFFF, 12)  # syncword
    w.write(0, 1)  # ID
    w.write(0, 2)  # layer
    w.write(protection_absent, 1)
    w.write(1, 2)  # profile (AAC LC)
    w.write(4, 4)  # sampling_frequency_index (44100)
    w.write(0, 1)  # private_bit
    w.write(channel_config, 3)
    w.write(0, 1)  # original_copy
    w.write(0, 1)  # home
    w.write(0, 2)  # copyright bits
    w.write(frame_length, 13)
    w.write(0x7FF, 11)  # adts_buffer_fullness
    w.write(nordbif, 2)
    return w.tobytes() + crc + payload


def _pce_stream(frames=6, front_cpe=1, lfe=0, payload_size=100):
    payload = _pce(front_cpe, lfe) + b"\x11" * payload_size
    return b"".join(
        _adts_frame(payload, channel_config=0) for _ in range(frames))


def _crc_stream(frames=6, nordbif=1, block_size=50):
    """ADTS stream with crc protection and nordbif+1 raw data blocks
    (of block_size bytes each) per frame."""

    crc = b"\xaa\xbb"
    payload = b""
    for _ in range(nordbif + 1):
        payload += b"\x22" * block_size
        if nordbif != 0:
            payload += crc
    return b"".join(
        _adts_frame(payload, protection_absent=0, nordbif=nordbif, crc=crc)
        for _ in range(frames))


class TADTS(TestCase):

    def setUp(self):
        original = os.path.join(DATA_DIR, "empty.aac")
        self.filename = get_temp_copy(original)

        tag = ID3()
        tag.add(TIT1(text=[u"a" * 5000], encoding=3))
        tag.save(self.filename)

        self.aac = AAC(original)
        self.aac_id3 = AAC(self.filename)

    def tearDown(self):
        os.remove(self.filename)

    def test_channels(self):
        self.failUnlessEqual(self.aac.info.channels, 2)
        self.failUnlessEqual(self.aac_id3.info.channels, 2)

    def test_bitrate(self):
        self.failUnlessEqual(self.aac.info.bitrate, 3159)
        self.failUnlessEqual(self.aac_id3.info.bitrate, 3159)

    def test_sample_rate(self):
        self.failUnlessEqual(self.aac.info.sample_rate, 44100)
        self.failUnlessEqual(self.aac_id3.info.sample_rate, 44100)

    def test_length(self):
        self.failUnlessAlmostEqual(self.aac.info.length, 3.70, 2)
        self.failUnlessAlmostEqual(self.aac_id3.info.length, 3.70, 2)

    def test_not_my_file(self):
        self.failUnlessRaises(
            AACError, AAC,
            os.path.join(DATA_DIR, "empty.ogg"))

        self.failUnlessRaises(
            AACError, AAC,
            os.path.join(DATA_DIR, "silence-44-s.mp3"))

    def test_pprint(self):
        self.assertEqual(self.aac.pprint(), self.aac_id3.pprint())
        self.assertTrue("ADTS" in self.aac.pprint())


class TADIF(TestCase):

    def setUp(self):
        original = os.path.join(DATA_DIR, "adif.aac")
        self.filename = get_temp_copy(original)

        tag = ID3()
        tag.add(TIT1(text=[u"a" * 5000], encoding=3))
        tag.save(self.filename)

        self.aac = AAC(original)
        self.aac_id3 = AAC(self.filename)

    def tearDown(self):
        os.remove(self.filename)

    def test_channels(self):
        self.failUnlessEqual(self.aac.info.channels, 2)
        self.failUnlessEqual(self.aac_id3.info.channels, 2)

    def test_bitrate(self):
        self.failUnlessEqual(self.aac.info.bitrate, 128000)
        self.failUnlessEqual(self.aac_id3.info.bitrate, 128000)

    def test_sample_rate(self):
        self.failUnlessEqual(self.aac.info.sample_rate, 48000)
        self.failUnlessEqual(self.aac_id3.info.sample_rate, 48000)

    def test_length(self):
        self.failUnlessAlmostEqual(self.aac.info.length, 0.25, 2)
        self.failUnlessAlmostEqual(self.aac_id3.info.length, 0.25, 2)

    def test_not_my_file(self):
        self.failUnlessRaises(
            AACError, AAC,
            os.path.join(DATA_DIR, "empty.ogg"))

        self.failUnlessRaises(
            AACError, AAC,
            os.path.join(DATA_DIR, "silence-44-s.mp3"))

    def test_pprint(self):
        self.assertEqual(self.aac.pprint(), self.aac_id3.pprint())
        self.assertTrue("ADIF" in self.aac.pprint())


class TADTS_program_config_element(TestCase):

    def test_channels_stereo(self):
        info = AAC(BytesIO(_pce_stream(front_cpe=1))).info
        self.failUnlessEqual(info.channels, 2)
        self.failUnlessEqual(info.sample_rate, 44100)

    def test_channels_lfe(self):
        info = AAC(BytesIO(_pce_stream(front_cpe=1, lfe=1))).info
        self.failUnlessEqual(info.channels, 3)

    def test_truncated_pce(self):
        # frame is complete but the PCE in it is missing fields
        data = _adts_frame(_pce()[:2], channel_config=0)
        self.failUnlessRaises(AACError, AAC, BytesIO(data))
        try:
            AAC(BytesIO(data))
        except AACError as e:
            self.assertTrue("program_config_element" in str(e))

    def test_truncated_frame(self):
        # stream ends in the middle of the second frame
        data = _pce_stream()[:120]
        self.failUnlessRaises(AACError, AAC, BytesIO(data))
        try:
            AAC(BytesIO(data))
        except AACError as e:
            self.assertTrue("program_config_element" not in str(e))


class TADTS_crc(TestCase):

    def test_bitrate_multi_block(self):
        # two raw data blocks of 50 bytes per frame, crc protected
        info = AAC(BytesIO(_crc_stream(nordbif=1, block_size=50))).info
        self.failUnlessEqual(info.bitrate, (8 * 2 * 50 * 44100) // (2 * 1024))

    def test_length_multi_block(self):
        info = AAC(BytesIO(_crc_stream(frames=6, nordbif=1))).info
        self.failUnlessAlmostEqual(info.length, 6 * 2 * 1024 / 44100.0, 2)

    def test_bitrate_single_block(self):
        info = AAC(BytesIO(_crc_stream(nordbif=0, block_size=50))).info
        self.failUnlessEqual(info.bitrate, (8 * 50 * 44100) // 1024)
