"""Prepare bindings for a source install or npm pack, preserving the selected DSDL."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from binding_info import generator_info


ROOT = Path(__file__).resolve().parent
# The standard dsdl.js tracked before bindings exported their source fingerprints.
LEGACY_STANDARD_SHA256 = '7c6520cb59c581341f2d51bd5cf50b7cd39ec923830f93c62fdf5d814cf5f7f1'


def main():
    output = ROOT / 'dronecan' / 'dsdl.js'
    if output.is_file():
        digest = hashlib.sha256(output.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        if digest != LEGACY_STANDARD_SHA256:
            # Read provenance through the public API, including for custom builds outside Git.
            info = json.loads(subprocess.check_output([
                'node', '-p', "JSON.stringify(require('./dronecan/dsdl').bindingInfo ?? {})",
            ], cwd=ROOT, text=True))
            if not info.get('usesDefaultDsdl'):
                if info.get('generator', {}).get('sha256') == generator_info()['sha256']:
                    return
                sys.exit('Existing bindings have a different or unknown generator. Rebuild with '
                         'npm run build for standard DSDL or npm run build -- <namespace directories> '
                         'for your chosen definitions.')

    from dronecan_dsdljs import generate_js_bindings
    generate_js_bindings(str(output.parent), [])


if __name__ == '__main__':
    main()
