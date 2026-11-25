"""Run the JS suite against a fresh standard build with the package's actual entry points."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def main():
    # Node resolves both package-local and hoisted workspace dependencies from here.
    with tempfile.TemporaryDirectory(prefix='.dsdljs-test-', dir=ROOT) as directory:
        package = Path(directory)
        shutil.copy2(ROOT / 'package.json', package)
        shutil.copytree(ROOT / 'examples', package / 'examples')
        shutil.copytree(ROOT / 'dronecan', package / 'dronecan', ignore=shutil.ignore_patterns('dsdl.js'))
        (package / 'test').mkdir()
        tests = [shutil.copy2(source, package / 'test') for source in sorted((ROOT / 'test').glob('*.test.js'))]
        subprocess.run([sys.executable, '-B', str(ROOT / 'dronecan_dsdljs.py'),
                        '--output', str(package / 'dronecan')], check=True)
        return subprocess.run(['node', '--test', *sys.argv[1:], *tests], cwd=package).returncode


if __name__ == '__main__':
    sys.exit(main())
