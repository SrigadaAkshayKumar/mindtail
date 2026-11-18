"""Step 4 (optional): a simple, clean edit of each cut clip: smooth zooms, word-by-word captions
in the video's brand colours, and 1-2 subtle whooshes. Loudness normalised for phones.

    python run.py edit <project>                         # every clip, python engine
    python run.py edit <project> --clips 2               # one clip
    python run.py edit <project> --engine remotion       # same edit drawn by Remotion (python install.py --remotion)
    options: --no-zoom  --no-captions  --sfx auto|light|none  --no-upper  --caption-y 1270  --size 96

Writes edited/NN-title.mp4 (+ .srt captions file for platforms that want one).
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from . import brand as brandlib
from . import plan as planlib
from .common import ASSETS, H, ROOT, W, die, ffmpeg, load_json, need, project_dir, save_json
from .sfx import SFX_DIR

FONTS = ASSETS / 'fonts'


# ---------------- shared: audio mix ----------------

def mix_audio(clip_mp4, cues, out_wav, duration):
    """Voice + SFX cues -> loudness-normalised stereo wav (-14 LUFS, -1.5 dBTP)."""
    inputs = ['-i', str(clip_mp4)]
    chains = ['[0:a]aresample=48000,aformat=channel_layouts=stereo,'
              'highpass=f=70,acompressor=threshold=-20dB:ratio=2.5:attack=8:release=120:makeup=2[v]']
    labels = ['[v]']
    for k, c in enumerate(cues, 1):
        inputs += ['-i', str(SFX_DIR / c['file'])]
        delay = int(c['at'] * 1000)
        vol = c['gain_db'] + c.get('norm_db', 0)
        chains.append(f"[{k}:a]atrim=start={c['offset']:.3f}:duration={c['length']:.3f},asetpts=PTS-STARTPTS,"
                      f"aresample=48000,aformat=channel_layouts=stereo,volume={vol:.2f}dB,"
                      f"afade=t=out:st={max(0, c['length'] - 0.06):.3f}:d=0.06,adelay={delay}|{delay}[s{k}]")
        labels.append(f'[s{k}]')
    chains.append(''.join(labels) + f'amix=inputs={len(labels)}:normalize=0:duration=first,'
                  f'loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000,atrim=0:{duration:.3f}[out]')
    ffmpeg(*inputs, '-filter_complex', ';'.join(chains), '-map', '[out]', '-c:a', 'pcm_s16le', out_wav)


def write_srt(plan, path):
    def ts(t):
        ms = int(round(t * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'
    lines = []
    for i, g in enumerate(plan['captions'], 1):
        lines += [str(i), f"{ts(g['start'])} --> {ts(g['end'])}", ' '.join(w['text'] for w in g['words']), '']
    Path(path).write_text('\n'.join(lines), encoding='utf-8')


# ---------------- python engine ----------------

def ass_color(hex_rgb, alpha=0):
    r, g, b = brandlib.hex_to_rgb(hex_rgb)
    return f'&H{alpha:02X}{b:02X}{g:02X}{r:02X}'


def css_to_ass_size(px, font_file):
    """libass sizes text by (ascent + descent), CSS by the em box. Convert so both engines match."""
    import struct
    try:
        data = (FONTS / font_file).read_bytes()
        n = struct.unpack('>H', data[4:6])[0]
        tables = {data[12 + 16 * i:16 + 16 * i]: struct.unpack('>I', data[20 + 16 * i:24 + 16 * i])[0]
                  for i in range(n)}
        upm = struct.unpack('>H', data[tables[b'head'] + 18:tables[b'head'] + 20])[0]
        os2 = tables[b'OS/2']
        asc, desc = struct.unpack('>HH', data[os2 + 74:os2 + 78])   # usWinAscent / usWinDescent
        return round(px * (asc + desc) / upm)
    except Exception:
        return round(px * 1.2)


def write_ass(plan, path):
    st, br = dict(plan['caption_style']), plan['brand']
    st['size'] = css_to_ass_size(st['size'], st['font_file'])
    white, accent, outline = ass_color(br['text']), ass_color(br['accent']), ass_color(br['outline'])
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{st['font']},{st['size']},{white},{white},{outline},&H64000000,0,0,0,0,100,100,1,0,1,{st['outline']},3,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def t(sec):
        cs = int(round(sec * 100))
        h, cs = divmod(cs, 360000)
        m, cs = divmod(cs, 6000)
        s, cs = divmod(cs, 100)
        return f'{h}:{m:02d}:{s:02d}.{cs:02d}'
    events = []
    fps = plan['fps']
    for g in plan['captions']:
        g0 = g['start'] - 1 / fps
        parts = []
        for i, w in enumerate(g['words']):
            a = max(0, int((w['s'] - 1 / fps - g0) * 1000))
            nxt = g['words'][i + 1]['s'] if i + 1 < len(g['words']) else None
            b = int(((nxt if nxt is not None else g['end'] + 1) - g0) * 1000)
            col = accent if w.get('emph') else white
            # hidden until spoken, then pops up (vertical squash -> full + fade), active word in accent colour
            tag = (f'{{\\alpha&HFF&\\fscy60\\1c{accent}'
                   f'\\t({a},{a + 1},\\alpha&H00&)\\t({a},{a + 110},0.6,\\fscy100)'
                   f'\\t({b},{b + 1},\\1c{col})}}')
            parts.append(tag + w['text'].replace('{', '(').replace('}', ')'))
        text = f"{{\\pos({W // 2},{st['y']})}}" + ' '.join(parts)
        events.append(f"Dialogue: 0,{t(g0)},{t(g['end'])},Cap,,0,0,0,,{text}")
    Path(path).write_text(head + '\n'.join(events) + '\n', encoding='utf-8')


def render_python(clip_mp4, plan, audio_wav, out_mp4, workdir):
    need('ffmpeg')
    ass = workdir / f'{out_mp4.stem}.ass'
    write_ass(plan, ass)
    fonts_rel = os.path.relpath(FONTS, workdir).replace('\\', '/')
    vf = f"ass={ass.name}:fontsdir={fonts_rel}" if plan['captions'] else 'null'
    dec = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', str(clip_mp4), '-f', 'rawvideo', '-pix_fmt', 'bgr24',
                            '-r', str(plan['fps']), '-s', f'{W}x{H}', '-'], stdout=subprocess.PIPE)
    tmp = out_mp4.with_suffix('.part.mp4')
    enc = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}',
                            '-r', str(plan['fps']), '-i', '-', '-i', str(audio_wav), '-vf', vf,
                            '-map', '0:v', '-map', '1:a', '-c:v', 'libx264', '-preset', 'medium', '-crf', '18',
                            '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-shortest',
                            '-movflags', '+faststart', str(tmp.resolve())],
                           stdin=subprocess.PIPE, cwd=workdir)
    cam = plan['cam']
    size = W * H * 3
    prev = None
    f = 0
    while True:
        buf = dec.stdout.read(size)
        if len(buf) < size:
            break
        frame = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
        s, x, y = cam[min(f, len(cam) - 1)]
        if abs(s - 1) > 1e-4:
            M = np.float32([[s, 0, x - x * s], [0, s, y - y * s]])
            out = cv2.warpAffine(frame, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        else:
            out = frame
        # light motion blur only while the camera is moving fast (snap zooms)
        if prev is not None and f > 0:
            vel = abs(s - cam[min(f - 1, len(cam) - 1)][0])
            if 0.012 < vel < 0.08:
                out = cv2.addWeighted(out, 0.7, prev, 0.3, 0)
        prev = out
        enc.stdin.write(out.tobytes())
        f += 1
    enc.stdin.close()
    dec.wait()
    if enc.wait() != 0:
        die('python engine: ffmpeg encode failed')
    tmp.replace(out_mp4)


# ---------------- remotion engine ----------------

REMOTION = ROOT / 'remotion'


def render_remotion(clip_mp4, plan, audio_wav, out_mp4, workdir):
    npx = shutil.which('npx')
    if not npx:
        die('Node.js is needed for --engine remotion. Install Node, then: python install.py --remotion')
    if not (REMOTION / 'node_modules').exists():
        die('Remotion is not installed yet. Run: python install.py --remotion')
    pub = REMOTION / 'public'
    pub.mkdir(exist_ok=True)
    tag = f'clip-{os.getpid()}-{out_mp4.stem[:20]}.mp4'
    shutil.copy2(clip_mp4, pub / tag)
    font_pub = pub / 'fonts'
    font_pub.mkdir(exist_ok=True)
    ff = plan['caption_style']['font_file']
    if not (font_pub / ff).exists():
        shutil.copy2(FONTS / ff, font_pub / ff)
    props = dict(plan, src=tag)
    props_file = workdir / f'{out_mp4.stem}.props.json'
    save_json(props_file, props)
    silent = workdir / f'{out_mp4.stem}.remotion.mp4'
    cmd = [npx, 'remotion', 'render', 'src/index.ts', 'Clip', str(silent.resolve()),
           f'--props={props_file.resolve()}', '--muted', '--codec=h264', '--crf=18',
           '--concurrency=50%', '--log=error']
    r = subprocess.run(cmd, cwd=REMOTION, shell=(os.name == 'nt'))
    (pub / tag).unlink(missing_ok=True)
    if r.returncode != 0 or not silent.exists():
        die('remotion render failed (see output above)')
    ffmpeg('-i', silent, '-i', audio_wav, '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac',
           '-b:a', '192k', '-shortest', '-movflags', '+faststart', out_mp4)
    silent.unlink(missing_ok=True)


# ---------------- main ----------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('project')
    ap.add_argument('--clips', default=None)
    ap.add_argument('--engine', default='python', choices=['python', 'remotion'])
    ap.add_argument('--no-zoom', action='store_true')
    ap.add_argument('--no-captions', action='store_true')
    ap.add_argument('--sfx', default='auto', choices=['auto', 'light', 'none'])
    ap.add_argument('--no-upper', action='store_true', help='sentence case captions instead of UPPERCASE')
    ap.add_argument('--caption-y', type=int, default=1270, help='caption centre line in px (0-1920)')
    ap.add_argument('--size', type=int, default=96, help='caption font size in px')
    ap.add_argument('--out', default=None, help='output folder (default <project>/edited)')
    a = ap.parse_args()

    pdir = project_dir(a.project)
    clips_dir = pdir / 'clips'
    metas = sorted(clips_dir.glob('*.json'))
    if not metas:
        die('no cut clips yet. Run: python run.py cut ' + pdir.name)
    want = {int(x) for x in a.clips.split(',')} if a.clips else None
    out_dir = Path(a.out) if a.out else pdir / 'edited'
    out_dir.mkdir(parents=True, exist_ok=True)
    work = pdir / '.work'
    work.mkdir(exist_ok=True)

    from .cut import ensure_video
    brand = brandlib.resolve(pdir, ensure_video(pdir, load_json(pdir / 'project.json')))
    print(f"-> brand colours: accent {brand['accent']} ({brand['source']})")
    opts = {'zoom': not a.no_zoom, 'captions': not a.no_captions, 'sfx': a.sfx,
            'uppercase': not a.no_upper, 'caption_y': a.caption_y, 'size': a.size}
    done = []
    for mpath in metas:
        meta = load_json(mpath)
        if want and meta['id'] not in want:
            continue
        clip_mp4 = clips_dir / meta['file']
        out = out_dir / meta['file']
        t0 = time.time()
        print(f"-> editing clip {meta['id']}: {meta['title']} ({a.engine} engine)")
        plan = planlib.build(meta, brand, opts)
        save_json(work / f"{meta['name']}.plan.json", {k: v for k, v in plan.items() if k != 'cam'})
        wav = work / f"{meta['name']}.mix.wav"
        mix_audio(clip_mp4, plan['sfx'], wav, plan['duration'])
        (render_remotion if a.engine == 'remotion' else render_python)(clip_mp4, plan, wav, out, work)
        if plan['captions']:
            write_srt(plan, out.with_suffix('.srt'))
        wav.unlink(missing_ok=True)
        sfx = ', '.join(f"{c['role']}@{c['at'] + 0:.1f}s" for c in plan['sfx']) or 'none'
        print(f"   ok {out.name}  zooms:{len(plan['transitions'])}  captions:{len(plan['captions'])}  "
              f"sfx: {sfx}  ({time.time() - t0:.0f}s)")
        done.append(out)
    print(f'\nDONE: {len(done)} edited clip(s) in {out_dir}')


if __name__ == '__main__':
    main()
