"""Builds the edit plan for one clip: camera zooms, caption groups and sound-effect cues.

Both render engines (python and remotion) read the same plan, so they produce the same edit:
the camera is pre-computed per frame here, captions carry exact word times, and the audio mix
is shared. Only the drawing differs.

Zoom style (adapted from a tested short-form editing engine):
  * open on motion: 1.18 -> wide, a fast ease-out snap over 9 frames
  * every 3-5 s (on sentence ends) the framing alternates wide <-> punched-in, as a hard cut
  * camera cuts / spliced ranges always get a framing change (hides the jump)
  * one or two smooth "snap" zooms for emphasis
  * between changes a slow +0.03 push so the frame is never dead
  * scale is always around the speaker's face, so the face stays in place
"""
import re

from .common import FPS, H, W
from . import sfx as sfxlib

WIDE = [1.0, 1.04, 1.02]
PUNCH = [1.16, 1.22, 1.13, 1.2]
DRIFT = 0.03
OPEN_SCALE, OPEN_FRAMES = 1.18, 9
SNAP_FRAMES = 8

# ---------- easing (cubic-bezier, same curves as CSS / Remotion Easing.bezier) ----------


def bezier(x1, y1, x2, y2):
    def sample(a1, a2, t):
        return ((1 - 3 * a2 + 3 * a1) * t + (3 * a2 - 6 * a1)) * t * t + 3 * a1 * t

    def ease(x):
        if x <= 0:
            return 0.0
        if x >= 1:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(40):
            mid = (lo + hi) / 2
            if sample(x1, x2, mid) < x:
                lo = mid
            else:
                hi = mid
        return sample(y1, y2, (lo + hi) / 2)
    return ease


EASE_OUT = bezier(0.16, 1, 0.3, 1)     # "snap": fast then settles
EASE_IN_OUT = bezier(0.65, 0, 0.35, 1)
EASES = {'snap': EASE_OUT, 'smooth': EASE_IN_OUT}


def cam_at(keys, f):
    """Camera {s, x, y} at frame f from keyframes. A key's `ease` says how we ARRIVE at it:
    cut = jump at its frame, linear = glide from the previous key, snap/smooth = move during
    the `dur` frames that end at the key."""
    pi = 0
    for i, k in enumerate(keys):
        if k['f'] <= f:
            pi = i
    p = keys[pi]
    n = keys[pi + 1] if pi + 1 < len(keys) else None
    if n is None or f < p['f']:
        return p['s'], p['x'], p['y']
    k = 0.0
    if n['ease'] == 'linear':
        k = (f - p['f']) / max(1, n['f'] - p['f'])
    elif n['ease'] in EASES:
        d = n.get('dur', 12)
        r = min(1.0, max(0.0, (f - (n['f'] - d)) / d))
        k = EASES[n['ease']](r)
    return tuple(a + (b - a) * k for a, b in ((p['s'], n['s']), (p['x'], n['x']), (p['y'], n['y'])))


# ---------- helpers ----------

def focus_at(shots, t):
    for s in shots:
        if s['t0'] <= t < s['t1']:
            return s['focus']
    return shots[-1]['focus'] if shots else [W / 2, H * 0.4]


def beat_bounds(words, shots, splices, duration):
    """Times where the framing changes. Must-cuts: camera cuts and splices."""
    must = sorted({round(s['t0'], 3) for s in shots if s['t0'] > 0.3} | {s for s in splices if s > 0.3})
    soft = []
    for i, w in enumerate(words[:-1]):
        nxt = words[i + 1]
        if w['w'][-1:] in '.?!' or nxt['s'] - w['e'] > 0.45:
            soft.append(round(nxt['s'] - 0.03, 3))
    bounds, last = [], 0.0
    cands = sorted(set(must) | set(soft))
    for c in cands:
        if c >= duration - 1.2:
            break
        if c in must:
            if c - last >= 0.5:
                bounds.append(c)
                last = c
            continue
        nxt_must = next((m for m in must if m > c), duration)
        if c - last >= 2.8 and nxt_must - c >= 1.5:
            bounds.append(c)
            last = c
        elif c - last > 6.0:
            bounds.append(c)
            last = c
    # very long stretches with no sentence end: cut on a word start every ~4.5 s
    filled, prev = [], 0.0
    for b in bounds + [duration]:
        while b - prev > 7.0:
            target = prev + 4.5
            ws = min((w['s'] for w in words if w['s'] > prev + 3.0), key=lambda s: abs(s - target), default=None)
            if ws is None or ws >= b - 1.5:
                break
            filled.append(round(ws - 0.03, 3))
            prev = ws
        if b < duration:
            filled.append(b)
        prev = b
    return sorted(set(filled)), set(must)


def build_camera(meta):
    words, shots, dur = meta['words'], meta['shots'], meta['duration']
    fps = meta.get('fps', FPS)
    frames = int(round(dur * fps))
    bounds, must = beat_bounds(words, shots, meta.get('splices', []), dur)
    starts = [0.0] + bounds
    ends = bounds + [dur]
    keys, transitions = [], []
    wi = pi = 0
    snaps_left = 2 if dur > 25 else 1
    snap_after = dur * 0.3
    for b, (t0, t1) in enumerate(zip(starts, ends)):
        fx, fy = focus_at(shots, t0 + 0.05)
        f0, f1 = int(round(t0 * fps)), max(int(round(t0 * fps)) + 1, int(round(t1 * fps)) - 1)
        punched = b % 2 == 1
        if punched:
            s = PUNCH[pi % len(PUNCH)]
            pi += 1
        else:
            s = WIDE[wi % len(WIDE)]
            wi += 1
        if b == 0:
            keys.append({'f': 0, 's': OPEN_SCALE, 'x': fx, 'y': fy, 'ease': 'cut'})
            keys.append({'f': OPEN_FRAMES, 's': s, 'x': fx, 'y': fy, 'ease': 'snap', 'dur': OPEN_FRAMES})
            transitions.append({'t': 0.0, 'kind': 'open'})
        else:
            is_must = any(abs(t0 - m) < 0.05 for m in must)
            if punched and not is_must and snaps_left and t0 >= snap_after:
                keys.append({'f': f0 + SNAP_FRAMES, 's': s, 'x': fx, 'y': fy, 'ease': 'snap', 'dur': SNAP_FRAMES})
                transitions.append({'t': t0, 'kind': 'snap'})
                snaps_left -= 1
                snap_after = t0 + dur * 0.3
            else:
                keys.append({'f': f0, 's': s, 'x': fx, 'y': fy, 'ease': 'cut'})
                transitions.append({'t': t0, 'kind': 'cut'})
        keys.append({'f': f1, 's': round(s + DRIFT, 4), 'x': fx, 'y': fy, 'ease': 'linear'})
    cam = []
    for f in range(frames):
        s, x, y = cam_at(keys, f)
        cam.append([round(s, 4), round(x, 1), round(y, 1)])
    return keys, cam, transitions, list(zip(starts, ends))


# ---------- captions ----------

STRIP = re.compile(r'[.,;:]+$')


def display(word, upper):
    w = STRIP.sub('', word.strip())
    w = w.replace('"', '')
    return w.upper() if upper else w


def merge_tokens(words):
    """Whisper splits things like "$500" ",000" / "e" "-commerce" / "100" "%" into separate tokens."""
    out = []
    for w in words:
        t = w['w'].strip()
        if out and (t[:1] in ',%-&' or t.startswith('.0') or out[-1]['w'].endswith('-')) and len(t) > 0 \
                and w['s'] - out[-1]['e'] < 0.3:
            out[-1] = {**out[-1], 'w': (out[-1]['w'] + t).replace(' ', ''), 'e': w['e']}
        else:
            out.append(dict(w))
    return out


def caption_groups(meta, upper=True, max_words=3, max_chars=15, max_dur=1.6):
    words = merge_tokens(meta['words'])
    splices = meta.get('splices', [])
    emph = {e.lower().strip('.,!?') for e in meta.get('emphasis', [])}
    groups, cur = [], []

    def flush():
        if cur:
            groups.append(cur.copy())
            cur.clear()
    for i, w in enumerate(words):
        text = display(w['w'], upper)
        if not text:
            continue
        if cur:
            chars = sum(len(c['text']) + 1 for c in cur) + len(text)
            gap = w['s'] - cur[-1]['e']
            crosses = any(cur[-1]['e'] <= s <= w['s'] + 0.01 for s in splices)
            if len(cur) >= max_words or chars > max_chars or gap > 0.35 or \
                    w['e'] - cur[0]['s'] > max_dur or crosses:
                flush()
        cur.append({'text': text, 's': w['s'], 'e': w['e'],
                    'emph': w['w'].lower().strip('.,!?"') in emph})
        if w['w'][-1:] in '.?!':
            flush()
    flush()
    out = []
    for g, nxt in zip(groups, groups[1:] + [None]):
        end = g[-1]['e'] + 0.25
        if nxt is not None:
            end = nxt[0]['s'] if nxt[0]['s'] - g[-1]['e'] < 0.6 else min(end, nxt[0]['s'])
        end = min(end, meta['duration'])
        out.append({'start': round(g[0]['s'], 3), 'end': round(end, 3), 'words': g})
    return out


# ---------- sound effects ----------

def sfx_cues(transitions, beats, duration, mode='auto', fps=FPS):
    if mode == 'none':
        return []
    cues, used = [], set()

    def add(role, peak_at, gain_db, prefer_len=None):
        it = sfxlib.pick(role, prefer_len, used)
        if not it:
            return
        used.add((it['file'], it['variant']))
        offset, length = it['start'], it['length']
        at = peak_at - it['peak']
        if at < 0:
            offset, length, at = offset - at, length + at, 0.0
        length = min(length, duration - at)
        if length <= 0.05:
            return
        cues.append({'file': it['file'], 'role': role, 'offset': round(offset, 3), 'length': round(length, 3),
                     'at': round(at, 3), 'gain_db': gain_db, 'norm_db': it.get('norm_db', 0)})

    add('whoosh', OPEN_FRAMES / fps * 0.5, -15, prefer_len=0.9)          # opening zoom
    if mode == 'light':
        return cues
    snap = next((t for t in transitions if t['kind'] == 'snap'), None)
    if snap:                                                             # whoosh on the emphasis zoom
        add('whoosh', snap['t'] + SNAP_FRAMES / fps * 0.4, -17, prefer_len=0.9)
    return cues


# ---------- the plan ----------

def build(meta, brand, opts):
    fps = meta.get('fps', FPS)
    keys, cam, transitions, beats = build_camera(meta) if opts.get('zoom', True) else \
        ([], [[1.0, W / 2, H / 2]] * int(round(meta['duration'] * fps)), [], [(0, meta['duration'])])
    caps = caption_groups(meta, upper=opts.get('uppercase', True)) if opts.get('captions', True) else []
    return {
        'fps': fps, 'width': W, 'height': H,
        'duration': meta['duration'], 'frames': len(cam),
        'title': meta.get('title'),
        'camera_keys': keys, 'cam': cam,
        'captions': caps,
        'caption_style': {
            'font': opts.get('font', 'Montserrat ExtraBold'), 'font_file': opts.get('font_file', 'Montserrat-ExtraBold.ttf'),
            'size': opts.get('size', 96), 'y': opts.get('caption_y', 1270), 'outline': 8, 'uppercase': opts.get('uppercase', True),
        },
        'brand': brand,
        'sfx': sfx_cues(transitions, beats, meta['duration'], opts.get('sfx', 'auto'), fps),
        'transitions': transitions,
    }
