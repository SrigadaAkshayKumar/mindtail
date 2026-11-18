"""Shot-aware 16:9 -> 9:16 reframing: find camera cuts, find the speaker's face in each shot,
and build an ffmpeg filter that crops each shot around the face (static crop per shot, like a
human editor would, with no jittery tracking)."""
import re
import subprocess

import cv2
import numpy as np

from .common import ASSETS, FPS, H, W

# YuNet face detector (OpenCV Zoo, MIT licence): small, fast, and handles turned heads and small faces
YUNET = ASSETS / 'models' / 'face_detection_yunet_2023mar.onnx'
_DET = {}
try:
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
except Exception:
    pass


def _detector(w, h):
    if 'yunet' not in _DET:
        _DET['yunet'] = cv2.FaceDetectorYN.create(str(YUNET), '', (w, h), 0.6, 0.3, 5000)
    d = _DET['yunet']
    d.setInputSize((w, h))
    return d


def scene_cuts(video, start, dur, threshold=0.30, min_shot=0.8):
    """Return shot boundaries [(a, b), ...] in seconds relative to `start`."""
    cmd = ['ffmpeg', '-hide_banner', '-ss', f'{start:.3f}', '-t', f'{dur:.3f}', '-i', str(video),
           '-vf', f"scale=320:-2,select='gt(scene,{threshold})',showinfo", '-an', '-f', 'null', '-']
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    times = [float(m) for m in re.findall(r'pts_time:([0-9.]+)', r.stderr)]
    bounds = [0.0]
    for t in times:
        if t - bounds[-1] >= min_shot and dur - t >= min_shot:
            bounds.append(t)
    bounds.append(dur)
    return list(zip(bounds[:-1], bounds[1:]))


def _faces(img):
    """All face boxes (x, y, w, h) in a BGR image."""
    h, w = img.shape[:2]
    _, faces = _detector(w, h).detect(img)
    if faces is None:
        return []
    return [tuple(float(v) for v in f[:4]) for f in faces if f[2] >= 18]


def face_in_shot(cap, t0, t1, samples=5):
    """Median face centre (cx, cy as 0..1) and size (0..1 of frame height), or None."""
    pts = []
    for k in range(samples):
        t = t0 + (t1 - t0) * (k + 0.5) / samples
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        h0, w0 = frame.shape[:2]
        scale = 640 / w0
        small = cv2.resize(frame, (640, int(h0 * scale)))
        faces = _faces(small)
        if faces:
            x, y, w, h = max(faces, key=lambda b: b[2] * b[3])
            sh = small.shape[0]
            pts.append(((x + w / 2) / 640, (y + h / 2) / sh, h / sh))
    if len(pts) < max(2, samples // 3):
        return None
    a = np.array(pts)
    return tuple(float(v) for v in np.median(a, axis=0))


def analyse_range(video, start, dur, src_w, src_h):
    """Shots for one source range: [{'a','b','face': (cx,cy,size)|None}] (times relative to start)."""
    shots = scene_cuts(video, start, dur)
    cap = cv2.VideoCapture(str(video))
    out = []
    for a, b in shots:
        out.append({'a': a, 'b': b, 'face': face_in_shot(cap, start + a, start + b)})
    cap.release()
    return out


def crop_width(src_w, src_h):
    return min(src_w, int(src_h * 9 / 16) // 2 * 2)


def crop_x(cx, src_w, src_h):
    cw = crop_width(src_w, src_h)
    return int(min(max(cx * src_w - cw / 2, 0), src_w - cw)) // 2 * 2


def plan_shots(shots, src_w, src_h, min_fit=1.0):
    """Decide a crop (or 'fit' layout) for each shot. A shot with no face (quote card, slide, screen
    recording, wide b-roll) is shown whole over a blurred background, so no text gets cut off.
    Very short faceless shots (< min_fit s, usually a missed detection) reuse the nearest face."""
    is_vertical = src_w / src_h < 0.75
    known = [s['face'] for s in shots if s['face']]
    plan, last = [], (known[0] if known else None)
    for s in shots:
        face = s['face'] or (last if s['b'] - s['a'] < min_fit else None)
        if s['face']:
            last = s['face']
        if is_vertical:
            mode, x0, fx, fy = 'vertical', 0, (face[0] if face else 0.5) * W, (face[1] if face else 0.4) * H
        elif face is None:
            mode, x0, fx, fy = 'fit', 0, W / 2, H * 0.42
        else:
            cw = crop_width(src_w, src_h)
            x0 = crop_x(face[0], src_w, src_h)
            mode = 'crop'
            fx = (face[0] * src_w - x0) / cw * W
            fy = face[1] * H
        plan.append({**s, 'mode': mode, 'x0': x0, 'focus': [round(fx), round(fy)]})
    return plan


def shot_filter(inp, shot, src_w, src_h, label, fps=FPS):
    """ffmpeg filter chain turning one shot of input `inp` into 1080x1920 [label]."""
    trim = f"trim=start={shot['a']:.3f}:end={shot['b']:.3f},setpts=PTS-STARTPTS"
    tail = f'setsar=1,fps={fps},format=yuv420p'
    if shot['mode'] == 'vertical':
        return (f"[{inp}]{trim},scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={W}:{H},{tail}[{label}]")
    if shot['mode'] == 'fit':
        return (f"[{inp}]{trim},split[{label}b][{label}f];"
                f"[{label}b]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                f"boxblur=30:3,eq=brightness=-0.08[{label}bb];"
                f"[{label}f]scale={W}:-2:flags=lanczos[{label}ff];"
                f"[{label}bb][{label}ff]overlay=0:(H-h)/2*0.85,{tail}[{label}]")
    cw = crop_width(src_w, src_h)
    return (f"[{inp}]{trim},crop={cw}:{src_h}:{shot['x0']}:0,scale={W}:{H}:flags=lanczos,"
            f"{tail}[{label}]")
