"""Caption colours that fit the video's branding.

    python run.py brand <project>                       # auto: pick an accent from the video's own colours
    python run.py brand <project> --accent "#FFE135"    # override (e.g. the creator's known brand colour)
    python run.py brand <project> --accent "#FFE135" --text "#FFFFFF" --note "Known brand yellow"

Writes output/<project>/brand.json, which the edit step reads.
Order of preference (Claude decides, see the skill): 1) the creator's known brand caption colour,
2) the strongest non-skin colour in the video (graphics, set lights, clothing), 3) a safe default.
"""
import argparse
import colorsys

import cv2
import numpy as np

from .common import die, load_json, project_dir, save_json

DEFAULT_ACCENT = '#FFD60A'   # classic short-form highlight yellow, readable on anything with a black outline


def hex_to_rgb(h):
    h = h.lstrip('#')
    if len(h) != 6:
        die(f'bad colour {h!r}, use #RRGGBB')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return '#' + ''.join(f'{int(max(0, min(255, c))):02X}' for c in rgb)


def vivid(rgb, min_s=0.55, min_v=0.92):
    """Push a colour to be bright and saturated enough to read as caption text with a dark outline."""
    r, g, b = (c / 255 for c in rgb)
    hh, s, v = colorsys.rgb_to_hsv(r, g, b)
    s, v = max(s, min_s), max(v, min_v)
    return tuple(round(c * 255) for c in colorsys.hsv_to_rgb(hh, s, v))


def sample_frames(video, n=24):
    cap = cv2.VideoCapture(str(video))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    frames = []
    for k in range(n):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * (k + 0.5) / n))
        ok, f = cap.read()
        if ok:
            frames.append(cv2.resize(f, (320, int(320 * f.shape[0] / f.shape[1]))))
    cap.release()
    return frames


def palette_from_video(video):
    """Return (accent_hex or None, palette list) from saturated, non-skin pixels."""
    frames = sample_frames(video)
    if not frames:
        return None, []
    px = []
    for f in frames:
        hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
        ycc = cv2.cvtColor(f, cv2.COLOR_BGR2YCrCb)
        sat = hsv[..., 1] > 120
        bright = hsv[..., 2] > 110
        skin = (ycc[..., 1] > 133) & (ycc[..., 1] < 178) & (ycc[..., 2] > 77) & (ycc[..., 2] < 130)
        m = sat & bright & ~skin
        px.append(f[m])
    pts = np.concatenate(px).astype(np.float32) if px else np.zeros((0, 3), np.float32)
    total = sum(f.shape[0] * f.shape[1] for f in frames)
    if len(pts) < total * 0.004:          # basically no strong colour anywhere
        return None, []
    k = min(5, max(1, len(pts) // 500))
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1.0)
    _, labels, centers = cv2.kmeans(pts, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.ravel(), minlength=k)
    pal = []
    for c, cnt in zip(centers, counts):
        b, g, r = c
        _, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        pal.append({'hex': rgb_to_hex((r, g, b)), 'share': round(float(cnt) / total, 4),
                    'score': float(cnt) * (s ** 1.5) * v})
    pal.sort(key=lambda p: -p['score'])
    best = hex_to_rgb(pal[0]['hex'])
    return rgb_to_hex(vivid(best)), pal


def resolve(pdir, video=None):
    """brand.json if present, else auto from `video`, else default. Always returns a dict."""
    b = load_json(pdir / 'brand.json')
    if b:
        return b
    accent, pal = palette_from_video(video) if video else (None, [])
    b = {'accent': accent or DEFAULT_ACCENT, 'text': '#FFFFFF', 'outline': '#000000',
         'source': 'video-colours' if accent else 'default',
         'palette': [p['hex'] for p in pal]}
    save_json(pdir / 'brand.json', b)
    return b


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('project')
    ap.add_argument('--accent', help='#RRGGBB highlight colour')
    ap.add_argument('--text', default=None, help='#RRGGBB main caption colour (default white)')
    ap.add_argument('--outline', default=None, help='#RRGGBB outline colour (default black)')
    ap.add_argument('--note', default='', help='why this colour (e.g. "creator brand yellow")')
    ap.add_argument('--reset', action='store_true', help='forget brand.json and auto-detect again')
    a = ap.parse_args()
    pdir = project_dir(a.project)
    from .cut import ensure_video
    project = load_json(pdir / 'project.json')

    if a.reset and (pdir / 'brand.json').exists():
        (pdir / 'brand.json').unlink()
    if a.accent or a.text or a.outline:
        b = load_json(pdir / 'brand.json') or {}
        b.update({'accent': rgb_to_hex(hex_to_rgb(a.accent)) if a.accent else b.get('accent', DEFAULT_ACCENT),
                  'text': a.text or b.get('text', '#FFFFFF'), 'outline': a.outline or b.get('outline', '#000000'),
                  'source': 'override', 'note': a.note})
        save_json(pdir / 'brand.json', b)
    else:
        b = resolve(pdir, ensure_video(pdir, project))
    print(f"brand: accent {b['accent']}  text {b['text']}  outline {b['outline']}  ({b['source']})")
    if b.get('palette'):
        print('video palette (strongest first): ' + ', '.join(b['palette']))


if __name__ == '__main__':
    main()
