"""Generate a small service and compare both wire modes against the reference codec."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from dronecan_dsdljs import generate_js_bindings
from dronecan import dsdl
from dronecan.transport import CompoundValue, bytes_from_bits


class GeneratorSchemaTest(unittest.TestCase):
    def test_standard_build_excludes_user_vendor_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vendor = root / 'dronecan_vendor_specific_types' / 'com'
            (vendor / 'lab').mkdir(parents=True)
            (vendor / 'lab' / 'PrivateSample.uavcan').write_text('uint8 value\n')
            # PyDroneCAN scans this directory when its module is first imported.
            # Give the child its own home while retaining the parent's Python installation.
            env = dict(os.environ, HOME=tmp, USERPROFILE=tmp, PYTHONPATH=os.pathsep.join(sys.path))
            project = Path(__file__).resolve().parents[1]
            generator = [sys.executable, '-B', str(project / 'dronecan_dsdljs.py')]
            standard = root / 'standard'
            custom = root / 'custom'
            subprocess.run(generator + ['--output', str(standard)], env=env, check=True)
            subprocess.run(generator + ['--output', str(custom), str(vendor)], env=env, check=True)
            export = 'module.exports.com_lab_PrivateSample ='
            self.assertFalse(export in (standard / 'dsdl.js').read_text(), 'Standard build included the private type')
            self.assertTrue(export in (custom / 'dsdl.js').read_text(), 'Custom build omitted the requested type')

    def test_constant_uses_longest_field_prefix_in_either_declaration_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ns = root / 'probe'
            ns.mkdir()
            constants = 'uint8 STATUS_OK = 1\nuint8 STATUS_CODE_OK = 2\n'
            (ns / '42.Status.uavcan').write_text(
                constants + 'uint8 status\nuint8 status_code\n---\n' +
                constants + 'uint8 status_code\nuint8 status\n')
            out = root / 'bindings'
            shutil.copytree(Path(__file__).resolve().parents[1] / 'dronecan', out,
                            ignore=shutil.ignore_patterns('dsdl.js'))
            generate_js_bindings(str(out), [str(ns)])
            script = """
const assert = require('node:assert/strict');
const { probe_Status_Request, probe_Status_Response } = require('./bindings/dsdl');
for (const Type of [probe_Status_Request, probe_Status_Response]) {
    assert.deepEqual(Type.CONSTANTS, { status: { OK: 1 }, status_code: { OK: 2 } });
    const message = new Type();
    message.fields.status_code.value = 2;
    assert.equal(message.toObj().getConstant('status_code'), 'OK');
}
"""
            subprocess.run(['node', '-e', script], cwd=root, check=True)

    def test_service_unions_and_nested_arrays(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ns = root / 'probe'
            ns.mkdir()
            (ns / 'Item.uavcan').write_text('uint8[<=3] data\n')
            (ns / '41.Select.uavcan').write_text(
                '@union\nuint8 number\nItem[2] pair\n---\n'
                '@union\nbool flag\nuint4[<=3] samples\nItem[<=2] items\ntruncated uint8 counter\n')
            # Use the actual standalone generator with both request and response types.
            out = root / 'bindings'
            shutil.copytree(Path(__file__).resolve().parents[1] / 'dronecan', out,
                            ignore=shutil.ignore_patterns('dsdl.js'))
            generate_js_bindings(str(out), [str(ns)])
            types = {t.full_name: t for t in dsdl.parse_namespaces([str(ns)])}
            request = CompoundValue(types['probe.Select'], _mode='request')
            request.pair[0].data = [65]
            request.pair[1].data = [66, 67]
            response = CompoundValue(types['probe.Select'], _mode='response')
            response.samples = [1, 15]
            nested = CompoundValue(types['probe.Select'], _mode='response')
            item = CompoundValue(types['probe.Item'])
            item.data = [3, 4]
            nested.items.append(item)
            truncated = CompoundValue(types['probe.Select'], _mode='response')
            truncated.counter = 257
            expected = [[bytes(bytes_from_bits(m._pack(tao))).hex() for tao in [True, False]]
                        for m in [request, response, nested, truncated]]
            script = r"""
const assert = require('node:assert/strict');
const D = require('./bindings/dsdl');
const req = new D.probe_Select_Request();
req.unionFieldIndex.value = 1;
req.unionField.items[0].fields.data.fromString('A');
req.unionField.items[1].fields.data.fromString('BC');
const res = new D.probe_Select_Response();
res.unionFieldIndex.value = 1;
const Primitive = require('./bindings/primitive_type');
for (const n of [1, 15]) res.unionField.push(new Primitive(n, Primitive.KIND_UNSIGNED_INT, 4));
const nested = new D.probe_Select_Response();
nested.unionFieldIndex.value = 2;
const item = new D.probe_Item();
item.fields.data.fromString('\x03\x04');
nested.unionField.push(item);
const truncated = new D.probe_Select_Response();
truncated.unionFieldIndex.value = 3;
truncated.unionField.value = 257;
const expected = JSON.parse(process.argv[1]);
const hex = bits => {
    const bytes = Buffer.alloc(Math.ceil(bits.length / 8));
    bits.forEach((b, i) => { bytes[i >> 3] |= b << (7 - i % 8); });
    return bytes.toString('hex');
};
for (const [i, msg] of [req, res, nested, truncated].entries()) {
    for (const [j, tao] of [true, false].entries()) {
        const ref = expected[i][j];
        assert.equal(hex(msg.pack(tao)), ref);
        const decoded = msg.constructor.unpack(Buffer.from(ref, 'hex'), tao);
        assert.equal(decoded.unionFieldIndex.value, msg.unionFieldIndex.value);
        assert.equal(hex(decoded.pack(tao)), ref);
    }
}
"""
            subprocess.run(['node', '-e', script, json.dumps(expected)], cwd=root, check=True)

    def test_custom_service_constants_keep_exact_js_types(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ns = root / 'probe'
            ns.mkdir()
            (ns / '42.Limits.uavcan').write_text(
                'uint64 VALUE_SAFE = 9007199254740991\n'
                'uint64 VALUE_LARGE = 9007199254740993\n'
                'uint64 value\n'
                'float64 RATIO_LARGE = 9007199254740994.0\n'
                'float64 ratio\n'
                '---\n'
                'int64 LOW = -9223372036854775808\n'
                'int64 value\n')
            out = root / 'bindings'
            shutil.copytree(project / 'dronecan', out, ignore=shutil.ignore_patterns('dsdl.js'))
            generate_js_bindings(str(out), [str(ns)])
            # This generated package intentionally has no standard actuator command schema.
            script = """
const assert = require('node:assert/strict');
const { DSDL } = require('./bindings');
const request = new DSDL.probe_Limits_Request();
const response = new DSDL.probe_Limits_Response();
const { value, ratio } = request.constructor.CONSTANTS;
assert.equal(value.SAFE, Number.MAX_SAFE_INTEGER);
assert.equal(value.LARGE, 9007199254740993n);
assert.equal(ratio.LARGE, 9007199254740994);
request.fields.value.value = value.LARGE;
assert.equal(request.toObj().getConstant('value'), 'LARGE');
const low = response.constructor.CONSTANTS.value.LOW;
assert.equal(low, -9223372036854775808n);
response.fields.value.value = low;
assert.equal(response.toObj().getConstant('value'), 'LOW');
"""
            # Temporary bindings should see dependencies installed locally or hoisted above the project.
            module_dirs = [str(parent / 'node_modules') for parent in (project, *project.parents)]
            if os.environ.get('NODE_PATH'):
                module_dirs.append(os.environ['NODE_PATH'])
            env = dict(os.environ, NODE_PATH=os.pathsep.join(module_dirs))
            subprocess.run(['node', '-e', script], cwd=root, env=env, check=True)
