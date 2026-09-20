import unittest
from MegaSerial.protocol_profiles import ProtocolDecoder, preset, validate_profile, MAX_PACKET


class DecoderTests(unittest.TestCase):
    def test_zmonitor_all_channels_and_every_chunk_boundary(self):
        for channel in range(16):
            raw = bytes([0xc8, 0xc9 + channel]) + 'سلام|OK\nnext'.encode() + b'\xfa'
            for split in range(len(raw) + 1):
                d = ProtocolDecoder(preset('zmonitor'))
                result = d.feed(raw[:split]) + d.feed(raw[split:])
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0]['data'], raw)
                self.assertEqual(result[0]['panel_id'], f'{channel // 4 + 1}{channel % 4 + 1}')
                self.assertEqual(result[0]['device_channel'], str(channel))
                self.assertEqual(result[0]['panel_payload'], 'سلام|OK\nnext')

    def test_title_commands_and_empty_payload(self):
        d = ProtocolDecoder(preset('zmonitor'))
        for payload, expected in [(b'#title:GPS', {'title': 'GPS'}),
                                  (b'#TITLE_COLOR:red', {'color': 'red'}),
                                  (b'#TITLE_BGCOLOR:1,2,3', {'bg': '1,2,3'}),
                                  (b'#TITLE_STYLE:title=GPS;color=#00ff00;bg=black',
                                   {'title': 'GPS', 'color': '#00ff00', 'bg': 'black'}),
                                  (b'#TITLE_STYLE:{"title":"GPS","background":"red"}',
                                   {'title': 'GPS', 'bg': 'red'})]:
            ev = d.feed(b'\xc8\xd2' + payload + b'\xfa')[0]
            self.assertEqual(ev['panel_style'], expected)
            self.assertTrue(ev['panel_control'])
        self.assertEqual(d.feed(b'\xc8\xc9\xfa')[0]['panel_payload'], '')

    def test_noise_invalid_and_incomplete_are_preserved(self):
        d = ProtocolDecoder(preset('zmonitor'))
        raw = b'noise\xc8\xd2Hello\xfa\xc8\xc8broken\xfa\xc8\xd2\xff\xfa\xc8\xd2partial'
        events = d.feed(raw) + d.flush()
        self.assertEqual(b''.join(e['data'] for e in events), raw)
        self.assertTrue(any('protocol_diagnostic' in e for e in events))
        self.assertEqual(d.buffer, b'')

    def test_custom_text_mapping_and_extra_separators(self):
        p = {**preset('text'), 'prefix': '$', 'separator': ':', 'ending': '0D0A',
             'mapping': {'gps': '32'}}
        d = ProtocolDecoder(p)
        self.assertEqual(d.feed(b'$gps:hello:'), [])
        ev = d.feed(b'world\r\n')[0]
        self.assertEqual((ev['panel_id'], ev['panel_payload']), ('32', 'hello:world'))
        self.assertIsNone(d.feed(b'$unknown:OK\r\n')[0]['panel_id'])
        self.assertEqual(d.feed(b'$12:OK\r\n')[0]['panel_id'], '12')

    def test_custom_frame_offsets_encoding_and_split_markers(self):
        p = {**preset('frame'), 'start': 'AA BB', 'end': 'CC DD', 'channel_offset': 1,
             'payload_offset': 3, 'channel_bias': 10, 'encoding': 'latin-1', 'mapping': {'2': '21'}}
        raw = b'\xaa\xbb\x00\x0c\x00caf\xe9\xcc\xdd'
        for split in range(len(raw) + 1):
            d = ProtocolDecoder(p)
            result = d.feed(raw[:split]) + d.feed(raw[split:])
            self.assertEqual(result[0]['panel_id'], '21')
            self.assertEqual(result[0]['panel_payload'], 'café')

    def test_bounds_and_resynchronization(self):
        for kind in ('frame', 'text'):
            d = ProtocolDecoder(preset(kind))
            raw = (b'\xc8\xd2' if kind == 'frame' else b'@PANEL:32|') + b'x' * (MAX_PACKET + 1)
            events = d.feed(raw)
            self.assertLessEqual(len(d.buffer), MAX_PACKET)
            events += d.flush()
            self.assertEqual(b''.join(e['data'] for e in events), raw)
        d = ProtocolDecoder(preset('zmonitor'))
        events = d.feed(b'\xc8\xd2bad\xc8\xd2good\xfa')
        self.assertEqual(events[-1]['panel_payload'], 'good')

    def test_validation_and_preset_constants(self):
        for update in ({'kind': 'bad'}, {'start': ''}, {'mapping': {'a': '99'}},
                       {'payload_offset': 0}, {'encoding': 'bad'}, {'separator': ''}):
            with self.assertRaises(ValueError):
                validate_profile({**preset('frame'), **update})
        self.assertEqual(validate_profile({**preset('zmonitor'), 'start': 'AA'})['start'], 'C8')

    def test_concatenated_and_noise_bytes_survive_arbitrary_chunking(self):
        raw = b'boot\xc8\xc9one\xfa\xc8\xd2two\xfa\xc8\xd8three\xfanoise\xc8\xd2tail'
        for size in range(1, len(raw) + 1):
            d = ProtocolDecoder(preset('zmonitor'))
            events = []
            for i in range(0, len(raw), size):
                events.extend(d.feed(raw[i:i + size]))
            events.extend(d.flush())
            self.assertEqual(b''.join(e['data'] for e in events), raw)
            self.assertEqual([e['panel_payload'] for e in events if 'panel_payload' in e], ['one', 'two', 'three'])

    def test_marker_value_in_header_and_empty_payload(self):
        p = {**preset('frame'), 'mapping': {'200': '32'}}
        ev = ProtocolDecoder(p).feed(b'\xc8\xc8\xfa')[0]
        self.assertEqual(ev['panel_id'], '32')
        self.assertEqual(ev['panel_payload'], '')

    def test_custom_text_oversized_line_does_not_reinterpret_tail(self):
        d = ProtocolDecoder(preset('text'))
        events = d.feed(b'@PANEL:32|' + b'x' * MAX_PACKET)
        events += d.feed(b'@PANEL:12|tail\n@PANEL:32|good\n')
        self.assertEqual([e['panel_payload'] for e in events if 'panel_payload' in e], ['good'])

    def test_invalid_profile_and_style_leave_input_untouched(self):
        p = preset('zmonitor')
        import copy
        before = copy.deepcopy(p)
        validate_profile(p)
        self.assertEqual(p, before)
        raw = b'\xc8\xd2#TITLE_STYLE:{bad}\xfa'
        ev = ProtocolDecoder(p).feed(raw)[0]
        self.assertEqual(ev['data'], raw)
        self.assertIn('Invalid title-style JSON', ev['protocol_diagnostic'])

    def test_flush_resets_oversized_line_even_with_empty_buffer(self):
        d = ProtocolDecoder(preset('text'))
        d.feed(b'x' * (MAX_PACKET + 1))
        self.assertTrue(d.discard_line)
        d.flush()
        self.assertEqual(d.feed(b'@PANEL:32|fresh connection\n')[0]['panel_id'], '32')

    def test_frame_mapping_uses_decoded_decimal_channel_numbers(self):
        for channel in ('D2', '09', '16', '999999'):
            with self.assertRaises(ValueError):
                validate_profile({**preset('zmonitor'), 'mapping': {channel: '32'}})
