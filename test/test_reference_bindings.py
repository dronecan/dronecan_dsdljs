"""Check generated bindings against PyDroneCAN's installed standard definitions."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from dronecan_dsdljs import generate_js_bindings
from dronecan import TYPENAMES
from dronecan.transport import CompoundValue, bytes_from_bits


ROOT = Path(__file__).resolve().parents[1]

# Both halves of a vendor service have the same DTID but different payload layouts.
SAMPLES = {
    'com_hobbywing_esc_SetAngle_Request': {'option': 1, 'angle': 1025},
    'com_hobbywing_esc_SetAngle_Response': {'option': 1, 'angle': [257, 1025]},
    'dronecan_sensors_rc_RCInput': {'status': 3, 'quality': 213, 'id': 11, 'rcin': [1, 2048, 4095]},
    'ardupilot_indication_Button': {'button': 1, 'press_time': 230},
    'uavcan_protocol_param_ExecuteOpcode_Response': {'argument': -0x123456789a, 'ok': False},
}


def wire_cases(value):
    cases = []
    for tao in [True, False]:
        bits = value._pack(tao)
        cases.append({'tao': tao, 'bits': bits, 'hex': bytes_from_bits(bits).hex()})
    return cases


class ReferenceBindingsTest(unittest.TestCase):
    def test_standard_messages_and_services(self):
        # Use the reference registry, excluding schemas loaded from the user's vendor directories.
        standard_root = Path(TYPENAMES['uavcan.protocol.NodeStatus'].source_file).resolve().parents[2]
        types = [t for t in TYPENAMES.values() if standard_root in Path(t.source_file).resolve().parents]
        references = {}
        for t in types:
            modes = ['request', 'response'] if t.kind == t.KIND_SERVICE else [None]
            for mode in modes:
                key = t.full_name.replace('.', '_') + ('_' + mode.title() if mode else '')
                value = CompoundValue(t, _mode=mode)
                entry = {
                    'name': t.full_name, 'dtid': t.default_dtid, 'direction': mode,
                    'signature': str(t.get_data_type_signature()), 'defaults': wire_cases(value),
                }
                if key in SAMPLES:
                    for field, expected in SAMPLES[key].items():
                        setattr(value, field, expected)
                    entry.update(fields=SAMPLES[key], populated=wire_cases(value))
                references[key] = entry
        self.assertFalse(SAMPLES.keys() - references.keys(),
                         f'Missing PyDroneCAN reference types: {SAMPLES.keys() - references.keys()}')

        with tempfile.TemporaryDirectory() as tmp:
            bindings = Path(tmp) / 'dronecan'
            shutil.copytree(ROOT / 'dronecan', bindings, ignore=shutil.ignore_patterns('dsdl.js'))
            generate_js_bindings(str(bindings), [])
            subprocess.run(['node', str(ROOT / 'test' / 'reference-bindings.cjs'),
                            str(bindings / 'dsdl.js')], input=json.dumps(references), text=True, check=True)
