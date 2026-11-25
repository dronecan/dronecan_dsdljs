#!/usr/bin/env python
# encoding: utf-8
'''
    Author: Huibean Luo <huibean.luo@vimdrones.com>
'''

import sys
import os
import argparse

from importlib.util import find_spec
from pathlib import Path

# The JavaScript dronecan/ directory is also a Python namespace package.
# Find the reference checkout before Python caches that namespace on import.
dronecan_spec = find_spec("dronecan")
if dronecan_spec is None or dronecan_spec.origin is None:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "../pydronecan"))

try:
    import dronecan.dsdl
except ModuleNotFoundError as ex:
    if ex.name not in ("dronecan", "dronecan.dsdl"):
        raise
    sys.exit("Failed to import dronecan.dsdl, please install dronecan with 'python3 -m pip install dronecan'")

from dronecan_dsdljs_helpers import generate_dronecan_js


def standard_dsdl_dirs():
    # Wheels contain dsdl_specs. Source installs can use the DSDL checkout beside pydronecan.
    package = Path(dronecan.__file__).resolve().parent
    for root in (package / 'dsdl_specs', package.parent.parent / 'DSDL'):
        dirs = [root / namespace for namespace in ('uavcan', 'dronecan', 'ardupilot', 'com')]
        if all(path.is_dir() for path in dirs):
            if (root / 'cuav').is_dir():
                dirs.append(root / 'cuav')
            return [str(path) for path in dirs]
    raise FileNotFoundError("Standard DSDL definitions unavailable; pass the namespace directories explicitly")


def generate_js_bindings(output_dir, dsdl_dirs):
    # Ensure the output directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Generate the DSDL bindings
    try:
        messages = dronecan.dsdl.parse_namespaces(dsdl_dirs or standard_dsdl_dirs())
        if not dsdl_dirs:
            messages.sort(key=lambda dtype: dtype.full_name)

        # Generate the dronecan.js file
        generate_dronecan_js(output_dir, messages, uses_default_dsdl=not dsdl_dirs)
    except Exception as ex:
        print(f"Failed to generate DSDL bindings: {ex}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate DroneCAN DSDL bindings for JavaScript")
    parser.add_argument("--output", required=True, help="Output directory for generated bindings")
    parser.add_argument("dsdl_dirs", nargs='*',
                        help="DSDL namespace directories (default: PyDroneCAN standard definitions)")
    args = parser.parse_args()

    generate_js_bindings(args.output, args.dsdl_dirs)
