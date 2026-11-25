"""Check the provenance exported by generated CommonJS bindings."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from dronecan_dsdljs import generate_js_bindings


PROJECT = Path(__file__).resolve().parents[1]


class BindingInfoTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.ns = self.root / 'schemas' / 'probe'
        self.ns.mkdir(parents=True)
        self.definition = self.ns / '100.Sample.uavcan'
        self.definition.write_text('uint8 value\n')
        self.out = self.root / 'bindings'
        shutil.copytree(PROJECT / 'dronecan', self.out, ignore=shutil.ignore_patterns('dsdl.js'))

    def generate(self, *namespaces):
        generate_js_bindings(str(self.out), [str(ns) for ns in namespaces])
        script = """
const assert = require('node:assert/strict');
const DSDL = require('./dsdl');
assert.equal(DSDL.messages[100], DSDL.probe_Sample);
assert.ok(DSDL.bindingInfo);
assert.ok(!Object.keys(DSDL).includes('bindingInfo'));
console.log(JSON.stringify(DSDL.bindingInfo));
"""
        return json.loads(subprocess.check_output(['node', '-e', script], cwd=self.out))

    def test_version_and_gitless_input_are_reproducible(self):
        info = self.generate(self.ns)
        package = json.loads((PROJECT / 'package.json').read_text())
        self.assertEqual(info['generator']['name'], package['name'])
        self.assertEqual(info['generator']['version'], package['version'])
        self.assertRegex(info['generator']['sha256'], r'^[0-9a-f]{64}$')
        probe = info['dsdl']['probe']
        self.assertIsNone(probe['commit'])
        self.assertIsNone(probe['dirty'])
        self.assertRegex(probe['sha256'], r'^[0-9a-f]{64}$')
        original = (self.out / 'dsdl.js').read_bytes()
        copied = self.root / 'another' / 'probe'
        shutil.copytree(self.ns, copied)
        self.assertEqual(self.generate(copied), info)
        self.assertEqual((self.out / 'dsdl.js').read_bytes(), original)

    @unittest.skipUnless(shutil.which('git'), 'requires Git for the tracked DSDL fixture')
    def test_git_metadata_tracks_only_the_actual_dsdl_inputs(self):
        def git(*args):
            return subprocess.check_output([
                'git', '-c', 'user.name=Binding test', '-c', 'user.email=test@example.invalid',
                '-c', 'commit.gpgSign=false', '-c', 'core.hooksPath=unused-hooks', *args
            ], cwd=self.ns.parent, text=True).strip()

        git('init', '--quiet')
        git('add', 'probe')
        git('commit', '--quiet', '-m', 'Define the sample schema')
        reference = git('rev-parse', 'HEAD')
        clean = self.generate(self.ns)
        self.assertEqual(clean['dsdl']['probe']['commit'], reference)
        self.assertIs(clean['dsdl']['probe']['dirty'], False)
        (self.ns / 'notes.txt').write_text('Unrelated to generation\n')
        self.assertEqual(self.generate(self.ns), clean)
        git('add', 'probe/notes.txt')
        git('commit', '--quiet', '-m', 'Update unrelated notes')
        self.assertEqual(self.generate(self.ns), clean)
        self.definition.write_text('uint16 value\n')
        vendor = self.root / 'vendor'
        vendor.mkdir()
        (vendor / '101.Other.uavcan').write_text('uint32 value\n')
        dsdl = self.generate(self.ns, vendor)['dsdl']
        self.assertIsNone(dsdl['vendor']['commit'])
        dirty = dsdl['probe']
        self.assertEqual(dirty['commit'], reference)
        self.assertIs(dirty['dirty'], True)
        self.assertNotEqual(dirty['sha256'], clean['dsdl']['probe']['sha256'])
