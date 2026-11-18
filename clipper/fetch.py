"""Step 1: get the video's audio and transcribe it with word timestamps.

    python run.py fetch "https://www.youtube.com/watch?v=..."
    python run.py fetch "C:/videos/my-podcast.mp4"
    options: --model small.en|base.en|medium.en|small  --lang en|auto  --cookies-from-browser chrome

Creates output/<slug>/ with project.json, source/audio.*, transcript/words.json and transcript.txt.
Only the audio is downloaded here; the video is downloaded by `cut`, once clips are picked.
"""
import argparse
import os
import shutil
import sys
import time
from pathlib import Path

from .common import OUTPUT, die, ffmpeg, fmt_ts, load_json, probe, save_json, slugify

YTDLP_BASE = ['--no-progress', '--no-playlist', '--retries', '5', '--sleep-requests', '1']


def ytdlp(args, cookies_browser=None):
    import subprocess
    cmd = [sys.executable, '-m', 'yt_dlp', *YTDLP_BASE]
    if shutil.which('node'):
        cmd += ['--js-runtimes', 'node']
    if cookies_browser:
        cmd += ['--cookies-from-browser', cookies_browser]
    r = subprocess.run(cmd + args, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        err = r.stderr.strip().splitlines()[-8:]
        msg = '\n'.join(err)
        if "not a bot" in msg or 'Sign in to confirm' in msg:
            msg += ('\n\nYouTube asked for a sign-in check. Retry with your browser cookies, e.g.\n'
                    '  python run.py fetch <url> --cookies-from-browser chrome   (or firefox / edge)')
        die(f'yt-dlp failed:\n{msg}')
    return r.stdout


def is_url(s):
    return s.startswith('http://') or s.startswith('https://')


def download_audio(url, proj, cookies):
    import json
    meta = json.loads(ytdlp(['--dump-single-json', '--skip-download', url], cookies))
    title = meta.get('title') or 'video'
    slug = f"{slugify(title, 40)}-{meta.get('id', '')}".strip('-')
    pdir = proj or (OUTPUT / slug)
    src = pdir / 'source'
    src.mkdir(parents=True, exist_ok=True)
    existing = list(src.glob('audio.*'))
    if not existing:
        print(f'-> downloading audio: {title}')
        ytdlp(['-f', 'ba[ext=m4a]/ba/b', '-o', str(src / 'audio.%(ext)s'), url], cookies)
        existing = list(src.glob('audio.*'))
    if not existing:
        die('audio download produced no file')
    project = load_json(pdir / 'project.json', {}) or {}
    project.update({
        'source': url, 'kind': 'youtube', 'id': meta.get('id'), 'title': title,
        'channel': meta.get('channel') or meta.get('uploader'), 'channel_url': meta.get('channel_url'),
        'duration': meta.get('duration'), 'slug': pdir.name, 'audio': existing[0].name,
        'width': meta.get('width'), 'height': meta.get('height'),
    })
    if cookies:
        project['cookies_from_browser'] = cookies
    save_json(pdir / 'project.json', project)
    return pdir, project


def local_source(path):
    p = Path(path).expanduser().resolve()
    if not p.exists():
        die(f'file not found: {p}')
    pdir = OUTPUT / slugify(p.stem, 50)
    (pdir / 'source').mkdir(parents=True, exist_ok=True)
    info = probe(p)
    project = load_json(pdir / 'project.json', {}) or {}
    project.update({'source': str(p), 'kind': 'local', 'title': p.stem, 'channel': None,
                    'duration': info['duration'], 'slug': pdir.name, 'video': str(p),
                    'width': info.get('width'), 'height': info.get('height')})
    save_json(pdir / 'project.json', project)
    return pdir, project


def to_wav16k(src, dst):
    if not dst.exists():
        ffmpeg('-i', src, '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', dst)
    return dst


def detect_language(audio):
    from faster_whisper import WhisperModel
    m = WhisperModel('tiny', device='cpu', compute_type='int8')
    _, info = m.transcribe(audio[16000 * 30: 16000 * 90] if len(audio) > 16000 * 90 else audio,
                           language=None, beam_size=1)
    return info.language, info.language_probability


def transcribe(wav, model_name, lang, device):
    import soundfile as sf
    from faster_whisper import BatchedInferencePipeline, WhisperModel
    audio, sr = sf.read(str(wav), dtype='float32')
    if lang == 'auto':
        lang, prob = detect_language(audio)
        print(f'-> detected language: {lang} ({prob:.0%})')
    if lang != 'en' and model_name.endswith('.en'):
        model_name = model_name[:-3]
    print(f'-> transcribing with whisper "{model_name}" on {device} '
          f'(roughly 1/5 of the video length on a laptop CPU; the first run also downloads the model) ...')
    compute = 'int8' if device == 'cpu' else 'float16'
    model = WhisperModel(model_name, device=device, compute_type=compute,
                         cpu_threads=max(1, (os.cpu_count() or 4) - 1))
    # batched inference: ~2x faster than sequential on CPU with the same words (benchmarked)
    pipe = BatchedInferencePipeline(model=model)
    segments, info = pipe.transcribe(audio, language=lang, batch_size=8, beam_size=1, word_timestamps=True)
    words, total, last_print = [], info.duration or 1, time.time()
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append({'w': text, 's': round(w.start, 3), 'e': round(w.end, 3),
                              'p': round(w.probability, 3)})
        if time.time() - last_print > 20:
            print(f'   {seg.end / total:5.0%}  ({fmt_ts(seg.end)} / {fmt_ts(total)})', flush=True)
            last_print = time.time()
    return words, lang


def sentences(words, soft_max=30, hard_max=60, gap=0.8):
    """Group words into sentence lines for Claude to read. Long sentences are only broken at a comma
    (or at hard_max), so a line end is never mistaken for a sentence end."""
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        end_punct = w['w'][-1:] in '.?!'
        long_gap = nxt is not None and nxt['s'] - w['e'] > gap
        comma_break = len(cur) >= soft_max and w['w'][-1:] in ',;:'
        if nxt is None or end_punct or long_gap or comma_break or len(cur) >= hard_max:
            out.append({'s': cur[0]['s'], 'e': cur[-1]['e'], 'i0': i - len(cur) + 1, 'i1': i,
                        'text': ' '.join(x['w'] for x in cur)})
            cur = []
    return out


def write_transcript(pdir, words, project):
    tdir = pdir / 'transcript'
    save_json(tdir / 'words.json', words)
    lines = sentences(words)
    save_json(tdir / 'sentences.json', lines)
    head = [f"# {project.get('title')}", f"# channel: {project.get('channel') or '-'}",
            f"# duration: {fmt_ts(project.get('duration') or (words[-1]['e'] if words else 0))}",
            '# format: [start_seconds-end_seconds] text   (seconds are what clips.json uses)', '']
    body = [f"[{s['s']:.2f}-{s['e']:.2f}] {s['text']}" for s in lines]
    (tdir / 'transcript.txt').write_text('\n'.join(head + body) + '\n', encoding='utf-8')
    return tdir / 'transcript.txt', len(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('source', help='YouTube URL or local video file')
    ap.add_argument('--model', default='small.en', help='whisper model (default small.en)')
    ap.add_argument('--lang', default='auto', help='language code, or auto (default)')
    ap.add_argument('--device', default='cpu', help='cpu (default) or cuda')
    ap.add_argument('--cookies-from-browser', default=None, help='chrome / firefox / edge (if YouTube blocks)')
    ap.add_argument('--retranscribe', action='store_true')
    a = ap.parse_args()

    if is_url(a.source):
        pdir, project = download_audio(a.source, None, a.cookies_from_browser)
        audio_src = pdir / 'source' / project['audio']
    else:
        pdir, project = local_source(a.source)
        audio_src = Path(project['video'])

    tx = pdir / 'transcript' / 'transcript.txt'
    if tx.exists() and not a.retranscribe:
        print(f'-> transcript already exists (use --retranscribe to redo)')
    else:
        wav = to_wav16k(audio_src, pdir / 'source' / 'audio16k.wav')
        t0 = time.time()
        words, lang = transcribe(wav, a.model, a.lang, a.device)
        if not words:
            die('no speech found in this video')
        project['language'] = lang
        save_json(pdir / 'project.json', project)
        tx, n = write_transcript(pdir, words, project)
        print(f'-> {len(words)} words, {n} lines in {time.time() - t0:.0f}s')

    print('\nDONE')
    print(f'project:    {pdir.name}')
    print(f'transcript: {tx}')
    print('next: read the transcript, write clips.json, then  python run.py cut ' + pdir.name)


if __name__ == '__main__':
    main()
