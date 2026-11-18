"""One-time setup: creates a private Python environment (.venv) and checks your tools.

    python install.py            # Python deps + checks
    python install.py --remotion # also install the optional Remotion edit engine (needs Node.js)

Safe to run again at any time.
"""
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / '.venv'
PY = VENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')

INSTALL_HINTS = {
    'ffmpeg': {
        'nt': 'winget install -e --id Gyan.FFmpeg   (then open a NEW terminal)',
        'darwin': 'brew install ffmpeg',
        'linux': 'sudo apt install ffmpeg',
    },
    'node': {
        'nt': 'winget install -e --id OpenJS.NodeJS.LTS   (then open a NEW terminal)',
        'darwin': 'brew install node',
        'linux': 'sudo apt install nodejs npm',
    },
}


def hint(tool):
    key = 'nt' if os.name == 'nt' else ('darwin' if sys.platform == 'darwin' else 'linux')
    return INSTALL_HINTS[tool][key]


def main():
    ok = True
    print('== Claude Clipping Tool setup ==')

    if sys.version_info < (3, 10):
        print(f'[X] Python 3.10+ needed (you have {sys.version.split()[0]}).')
        sys.exit(1)
    print(f'[ok] Python {sys.version.split()[0]}')

    for tool in ('ffmpeg', 'ffprobe'):
        if shutil.which(tool):
            print(f'[ok] {tool}')
        else:
            ok = False
            print(f'[X] {tool} not found. Install it:  {hint("ffmpeg")}')

    if shutil.which('node'):
        print('[ok] node (helps YouTube downloads; needed only for the optional Remotion engine)')
    else:
        print(f'[!] node not found (recommended for reliable YouTube downloads):  {hint("node")}')

    if not PY.exists():
        print('-> creating .venv ...')
        venv.create(VENV, with_pip=True)
    print('-> installing Python packages (first time takes a few minutes) ...')
    subprocess.run([str(PY), '-m', 'pip', 'install', '--upgrade', 'pip', '-q'], check=False)
    r = subprocess.run([str(PY), '-m', 'pip', 'install', '-q', '-r', str(ROOT / 'requirements.txt')])
    if r.returncode != 0:
        ok = False
        print('[X] pip install failed (see the error above).')
    else:
        # YouTube changes often; keeping yt-dlp current fixes most download errors
        subprocess.run([str(PY), '-m', 'pip', 'install', '-q', '-U', 'yt-dlp[default]'], check=False)
        print('[ok] Python packages (yt-dlp up to date)')

    if '--remotion' in sys.argv:
        npm = shutil.which('npm')
        if not npm:
            ok = False
            print(f'[X] npm not found, the Remotion engine needs Node.js:  {hint("node")}')
        else:
            print('-> installing the Remotion engine (npm) ...')
            r = subprocess.run([npm, 'install', '--no-audit', '--no-fund'], cwd=ROOT / 'remotion',
                               shell=(os.name == 'nt'))
            ok = ok and r.returncode == 0
            print('[ok] Remotion engine' if r.returncode == 0 else '[X] npm install failed')

    print()
    print('Setup complete. Ask Claude:  clip this video: <youtube link>' if ok
          else 'Setup finished with problems, fix the [X] items above and run again.')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
