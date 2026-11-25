"""Identify the sources of a generated binding without embedding local paths."""

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import subprocess


GENERATOR_DIR = Path(__file__).resolve().parent
GENERATOR_SOURCES = (
    'binding_info.py', 'common.py', 'dronecan_dsdljs.py', 'dronecan_dsdljs_helpers.py',
    'dronecan_dsdljs_pack_generator.py', 'dronecan_dsdljs_unpack_generator.py',
)


def fingerprint(sources):
    # Include logical filenames: renaming a DSDL file can change its default DTID.
    encoded = json.dumps(sorted(sources), ensure_ascii=True, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('ascii')).hexdigest()


def git_revision(directory, paths):
    """Report the last commit touching these inputs and any local changes to them."""
    command = ['git', '--no-optional-locks', '-C', str(directory)]
    try:
        commit = subprocess.check_output(
            command + ['log', '-1', '--format=%H', '--', *paths], stderr=subprocess.DEVNULL
        ).decode('ascii').strip()
        if commit:
            changes = subprocess.check_output(
                command + ['status', '--porcelain=v1', '--ignored', '--untracked-files=all', '--', *paths],
                stderr=subprocess.DEVNULL,
            )
            return {'commit': commit, 'dirty': bool(changes)}
    except (OSError, subprocess.CalledProcessError):
        pass
    return {'commit': None, 'dirty': None}


def generator_info():
    package = json.loads((GENERATOR_DIR / 'package.json').read_text(encoding='utf-8'))
    generator = {'name': package['name'], 'version': package['version']}
    sources = [(name, (GENERATOR_DIR / name).read_text(encoding='utf-8')) for name in GENERATOR_SOURCES]
    sources.append(('package.json', [generator['name'], generator['version']]))
    generator.update(git_revision(GENERATOR_DIR, [*GENERATOR_SOURCES, 'package.json']))
    generator['sha256'] = fingerprint(sources)
    return generator


def binding_info(messages):
    schemas = defaultdict(list)
    roots = defaultdict(set)
    for message in messages:
        parts = message.full_name.split('.')
        namespace = parts[0]
        path = Path(message.source_file)
        logical_name = '/'.join([*parts[:-1], path.name])
        schemas[namespace].append((logical_name, message.source_text))
        roots[namespace].add(path.absolute().parents[len(parts) - 2])

    dsdl = {}
    for namespace in sorted(schemas):
        # A caller can supply parsed types from more than one checkout.
        directories = roots[namespace]
        revision = {'commit': None, 'dirty': None}
        if len(directories) == 1:
            revision = git_revision(next(iter(directories)), [':(glob)**/*.uavcan'])
        dsdl[namespace] = {**revision, 'sha256': fingerprint(schemas[namespace])}
    return {'generator': generator_info(), 'dsdl': dsdl}
