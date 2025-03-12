#!/usr/bin/env python
# encoding: utf-8
'''
    Author: Huibean Luo <huibean.luo@vimdrones.com>
'''

import sys
import os
import argparse

try:
    import dronecan.dsdl
except Exception as ex:
    # for usage in CI try with a local pydronecan path
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "../pydronecan/"))
    try:
        import dronecan.dsdl
    except Exception as ex:
        print(ex)
        print("Failed to import dronecan.dsdl, please install dronecan with 'python3 -m pip install dronecan'")
        sys.exit(1)

from dronecan_dsdljs_helpers import generate_dronecan_js

def generate_js_bindings(output_dir, dsdl_dirs):
    # Ensure the output directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Generate the DSDL bindings
    try:
        messages = dronecan.dsdl.parse_namespaces(dsdl_dirs)
        
        # Generate the dronecan.js file
        generate_dronecan_js(output_dir, messages)
    except Exception as ex:
        print(f"Failed to generate DSDL bindings: {ex}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate DroneCAN DSDL bindings for JavaScript")
    parser.add_argument("--output", required=True, help="Output directory for generated bindings")
    parser.add_argument("dsdl_dirs", nargs='+', help="Directories containing DSDL definitions")
    args = parser.parse_args()

    generate_js_bindings(args.output, args.dsdl_dirs)