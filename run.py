"""Single entry point. Always runs inside the project's .venv (created by install.py).

    python run.py fetch <youtube-url | local-file>       download audio + transcribe
    python run.py cut <project>                          cut the picked clips to 9:16
    python run.py edit <project> [--engine python|remotion] [--clips 1,3]
    python run.py find <project> "exact phrase"          word-accurate time of a phrase

Run `python run.py <command> -h` for the options of each step.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')

COMMANDS = {
    'fetch': 'clipper.fetch',
    'cut': 'clipper.cut',
    'brand': 'clipper.brand',
    'edit': 'clipper.edit',
    'find': 'clipper.find',
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    if not PY.exists():
        print('First run setup:  python install.py')
        sys.exit(1)
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1', PYTHONUNBUFFERED='1', HF_HUB_DISABLE_XET='1',
               HF_HUB_DISABLE_SYMLINKS_WARNING='1', HF_HUB_VERBOSITY='error')
    cmd = [str(PY), '-m', COMMANDS[sys.argv[1]], *sys.argv[2:]]
    sys.exit(subprocess.run(cmd, cwd=ROOT, env=env).returncode)


if __name__ == '__main__':
    main()
