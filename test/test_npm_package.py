"""Check npm lifecycle behavior without contacting a package registry."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

from binding_info import GENERATOR_SOURCES
from dronecan_dsdljs import dronecan


ROOT = Path(__file__).resolve().parents[1]


class NpmPackageTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.project = self.root / 'source'
        self.project.mkdir()
        for name in (*GENERATOR_SOURCES, 'prepare_bindings.py', 'package.json'):
            shutil.copy2(ROOT / name, self.project)
        shutil.copytree(ROOT / 'dronecan', self.project / 'dronecan', ignore=shutil.ignore_patterns('dsdl.js'))
        # Allow an installed PyDroneCAN or the same source checkout used by the test runner.
        python_path = [str(Path(dronecan.__file__).resolve().parents[1]), os.environ.get('PYTHONPATH', '')]
        self.env = dict(os.environ, PYTHONPATH=os.pathsep.join(python_path),
                        npm_config_cache=str(self.root / 'cache'), npm_config_offline='true')

    def run_in(self, directory, *args):
        subprocess.run(args, cwd=directory, env=self.env, check=True)

    @unittest.skipUnless(shutil.which('git'), 'requires a local Git repository')
    def test_git_install_prepares_bindings(self):
        # These binding assertions only use Node built-ins. Keep external packages out of this fixture.
        manifest = self.project / 'package.json'
        package = json.loads(manifest.read_text())
        package['dependencies'] = {}
        manifest.write_text(json.dumps(package))
        self.run_in(self.project, 'git', 'init', '--quiet')
        self.run_in(self.project, 'git', 'add', '.')
        self.run_in(self.project, 'git', '-c', 'user.name=Package Test', '-c', 'user.email=test@example.invalid',
                    '-c', 'commit.gpgSign=false', '-c', 'core.hooksPath=unused-hooks', 'commit', '-qm', 'Test package')
        app = self.root / 'app'
        app.mkdir()
        self.run_in(app, 'npm', 'install', '--no-fund', '--no-audit', 'git+' + self.project.as_uri())
        self.run_in(app, 'node', '-e', """
const assert = require('node:assert/strict');
const dsdl = require('dronecan_dsdljs/dronecan/dsdl');
assert.ok(dsdl.bindingInfo.generator.sha256);
assert.equal(new dsdl.uavcan_protocol_file_Read_Response().pack().length, 16);
""")

    def test_workspace_runner_resolves_hoisted_modules(self):
        (self.root / 'package.json').write_text(json.dumps({'private': True, 'workspaces': ['source']}))
        modules = self.root / 'node_modules'
        modules.mkdir()
        (modules / 'hoisted-probe.js').write_text('module.exports = 42;')
        shutil.copytree(ROOT / 'examples', self.project / 'examples')
        tests = self.project / 'test'
        tests.mkdir()
        shutil.copy2(ROOT / 'test' / 'run_js_tests.py', tests)
        (tests / 'workspace.test.js').write_text("""
const assert = require('node:assert/strict');
assert.equal(require('hoisted-probe'), 42);
assert.ok(require('../dronecan/dsdl').uavcan_protocol_NodeStatus);
""")
        self.run_in(self.root, 'npm', 'test', '--workspace', 'dronecan_dsdljs')
        self.assertFalse((self.project / 'node_modules').exists())

    def test_pack_preserves_explicit_build(self):
        vendor = self.root / 'vendor'
        vendor.mkdir()
        (vendor / '110.Sample.uavcan').write_text('uint8 reading\n')
        self.run_in(self.project, 'npm', 'run', 'build', '--', str(vendor))
        binding = self.project / 'dronecan' / 'dsdl.js'
        expected = binding.read_bytes()
        self.run_in(self.project, 'npm', 'pack', '--silent', '--pack-destination', str(self.root))
        archive, = self.root.glob('*.tgz')
        with tarfile.open(archive) as package:
            self.assertEqual(package.extractfile('package/dronecan/dsdl.js').read(), expected)
        self.assertEqual(binding.read_bytes(), expected)
