"""Mood edit: a cinematic 9:16 montage of short gameplay shots, made for a song added later on the platform.

    python run.py mood <spec.json> [--only name] [--preview song.mp3]

spec.json = {"source": "input/stream.mp4", "out": "output/<dir>", "game_volume": 0.12,
             "crop_h": 990, "edits": [{"name": "nine-months-ago", "hook": "SHE HAD NOTHING LEFT",
             "end": "optional closing text", "shots": [[start_s, dur_s, x_centre_0_to_1?], ...]}]}

Every shot: a 9:16 crop (top crop_h rows, so in-game subtitles at the bottom stay out), a slow push-in, a dark
cinematic grade, vignette and fine grain. Hard cuts (time them to the song when you have it), a fade in/out,
the hook as on-screen text for the first seconds. The game audio is kept quiet (game_volume) so the platform's
song carries the clip; --preview mixes a song in for checking only (never upload that file).
"""
import argparse
import json
import sys
from pathlib import Path

from .common import W, H, ROOT, die, ffmpeg

FONT = ROOT / 'assets' / 'fonts' / 'Montserrat-Black.ttf'


def esc(text):
    return text.replace('\\', '\\\\').replace(':', '\\:').replace("'", '’').replace('%', '\\%')


def shot_chain(i, shot, crop_h, src_w, fps):
    start, dur = shot[0], shot[1]
    xc = shot[2] if len(shot) > 2 else 0.5
    cw = int(crop_h * 9 / 16) // 2 * 2
    x0 = int(min(max(xc * src_w - cw / 2, 0), src_w - cw)) // 2 * 2
    zoom = 0.06
    return (f'[{i}:v]crop={cw}:{crop_h}:{x0}:0,scale={W}:{H}:flags=lanczos,'
            f"scale=w='trunc({W}*(1+{zoom}*t/{dur})/2)*2':h='trunc({H}*(1+{zoom}*t/{dur})/2)*2':eval=frame,"
            f'crop={W}:{H},setsar=1,fps={fps},'
            f'eq=contrast=1.1:brightness=0.0:saturation=0.9:gamma=1.04,'
            f"colorbalance=bs=0.05:bm=0.02:rh=0.02,vignette=PI/4.5,noise=alls=5:allf=t,format=yuv420p[v{i}];"
            f'[{i}:a]aresample=48000,asetpts=PTS-STARTPTS[a{i}]')


def render(spec, edit, src, out_dir, preview=None):
    shots = edit['shots']
    crop_h = spec.get('crop_h', 990)
    src_w = spec.get('src_w', 1920)
    fps = spec.get('fps', 30)
    vol = spec.get('game_volume', 0.12)
    inputs, chains = [], []
    for i, sh in enumerate(shots):
        inputs += ['-ss', f'{sh[0]:.3f}', '-t', f'{sh[1]:.3f}', '-i', str(src)]
        chains.append(shot_chain(i, sh, crop_h, src_w, fps))
    n = len(shots)
    total = sum(s[1] for s in shots)
    chains.append(''.join(f'[v{i}][a{i}]' for i in range(n)) + f'concat=n={n}:v=1:a=1[cv][ca]')
    text = []
    hook = edit.get('hook')
    if hook:
        lines = hook.split('\n')
        for k, line in enumerate(lines):
            y = 300 + k * 92
            text.append(f"drawtext=fontfile='{FONT}':text='{esc(line)}':fontsize=74:fontcolor=white:"
                        f"borderw=0:shadowcolor=black@0.7:shadowx=0:shadowy=4:x=(w-text_w)/2:y={y}:"
                        f"alpha='if(lt(t,0.15),t/0.15,if(lt(t,2.6),1,if(lt(t,3.1),(3.1-t)/0.5,0)))'")
    end = edit.get('end')
    if end:
        t0 = total - 2.6
        text.append(f"drawtext=fontfile='{FONT}':text='{esc(end)}':fontsize=60:fontcolor=white:"
                    f"shadowcolor=black@0.7:shadowy=4:x=(w-text_w)/2:y=h*0.42:"
                    f"alpha='if(lt(t,{t0}),0,if(lt(t,{t0 + 0.4}),(t-{t0})/0.4,1))'")
    vf = ','.join(text + [f'fade=t=in:d=0.25', f'fade=t=out:st={total - 0.5:.2f}:d=0.5'])
    chains.append(f'[cv]{vf}[outv]')
    chains.append(f'[ca]volume={vol},afade=t=in:d=0.3,afade=t=out:st={total - 0.6:.2f}:d=0.6[outa]')
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{edit['name']}.mp4"
    ffmpeg(*inputs, '-filter_complex', ';'.join(chains), '-map', '[outv]', '-map', '[outa]',
           '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', str(fps),
           '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', out)
    print(f'   ok {out.name}  {total:.1f}s, {n} shots')
    if preview:
        pv = out_dir / f"{edit['name']}.PREVIEW-with-song-do-not-upload.mp4"
        ffmpeg('-i', out, '-i', preview, '-filter_complex',
               f'[1:a]atrim=0:{total},afade=t=out:st={total - 1}:d=1,volume=0.9[s];[0:a][s]amix=inputs=2:normalize=0[a]',
               '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', pv)
        print(f'   preview {pv.name}')
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('spec')
    ap.add_argument('--only', default=None, help='comma list of edit names')
    ap.add_argument('--preview', default=None, help='a song file to mix in for a preview copy (never upload it)')
    a = ap.parse_args()
    spec = json.loads(Path(a.spec).read_text())
    src = ROOT / spec['source'] if not Path(spec['source']).is_absolute() else Path(spec['source'])
    if not src.exists():
        die(f'source video not found: {src}')
    out_dir = ROOT / spec['out']
    want = set(a.only.split(',')) if a.only else None
    for edit in spec['edits']:
        if want and edit['name'] not in want:
            continue
        print(f"-> {edit['name']}")
        render(spec, edit, src, out_dir, a.preview)


if __name__ == '__main__':
    sys.exit(main())
