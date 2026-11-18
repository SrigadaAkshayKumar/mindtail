"""Shared helpers: paths, json, ffmpeg/ffprobe wrappers."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / 'output'
ASSETS = ROOT / 'assets'
FPS = 30          # default / maximum output frame rate
W, H = 1080, 1920


def die(msg):
    print(f'ERROR: {msg}', file=sys.stderr)
    sys.exit(1)


def slugify(text, maxlen=50):
    text = re.sub(r'[^\w\s-]', '', text, flags=re.UNICODE).strip().lower()
    text = re.sub(r'[\s_-]+', '-', text)
    return text[:maxlen].strip('-') or 'video'


def load_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


def project_dir(name_or_path):
    """Accepts a project folder name (inside output/) or a path."""
    p = Path(name_or_path)
    if p.is_dir() and (p / 'project.json').exists():
        return p.resolve()
    q = OUTPUT / name_or_path
    if (q / 'project.json').exists():
        return q
    die(f'project not found: {name_or_path}  (look inside {OUTPUT})')


def need(tool):
    if not shutil.which(tool):
        die(f'{tool} is not installed or not on PATH. Run: python install.py')


def run(cmd, quiet=True, check=True):
    """Run a command; on failure print the tail of stderr."""
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    if check and r.returncode != 0:
        tail = '\n'.join((r.stderr or r.stdout).strip().splitlines()[-25:])
        die(f'command failed: {" ".join(str(c) for c in cmd[:6])} ...\n{tail}')
    if not quiet and r.stdout:
        print(r.stdout)
    return r


def ffmpeg(*args):
    need('ffmpeg')
    return run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', *args])


def probe(path):
    need('ffprobe')
    r = run(['ffprobe', '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', path])
    info = json.loads(r.stdout)
    v = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
    out = {'duration': float(info['format'].get('duration', 0))}
    if v:
        num, den = (v.get('avg_frame_rate') or '30/1').split('/')
        rot = 0
        for sd in v.get('side_data_list', []) or []:
            rot = int(sd.get('rotation', 0) or 0)
        w, h = int(v['width']), int(v['height'])
        if abs(rot) in (90, 270):
            w, h = h, w
        out.update(width=w, height=h, fps=float(num) / float(den or 1) if float(den or 1) else 30.0)
    return out


def out_fps(src_fps):
    """Keep the source frame rate (24/25/30) so motion stays smooth; bring 50/60 fps down to 30."""
    for f in (24, 25, 30):
        if abs(src_fps - f) < 0.6 or abs(src_fps - f * 1000 / 1001) < 0.05:
            return f
    return FPS


def fmt_ts(t):
    m, s = divmod(max(0.0, t), 60)
    h, m = divmod(int(m), 60)
    return f'{h}:{m:02d}:{s:04.1f}' if h else f'{m}:{s:04.1f}'
