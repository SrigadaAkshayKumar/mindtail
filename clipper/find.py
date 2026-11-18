"""Find the exact time of a phrase in the transcript (word-accurate), for precise clip starts/ends.

    python run.py find <project> "the thing that separates winners"
    python run.py find <project> "never give it to you" --near 470

Prints every match: start time of its first word and end time of its last word.
"""
import argparse
import re

from .common import fmt_ts, load_json, project_dir


def norm(t):
    return re.sub(r"[^\w$%']+", '', t.lower())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('project')
    ap.add_argument('phrase')
    ap.add_argument('--near', type=float, default=None, help='only matches within 60 s of this time')
    a = ap.parse_args()
    words = load_json(project_dir(a.project) / 'transcript' / 'words.json')
    toks = [norm(w['w']) for w in words]
    target = [norm(t) for t in a.phrase.split() if norm(t)]
    hits = 0
    for i in range(len(toks) - len(target) + 1):
        if toks[i:i + len(target)] == target:
            s, e = words[i]['s'], words[i + len(target) - 1]['e']
            if a.near is not None and abs(s - a.near) > 60:
                continue
            ctx = ' '.join(w['w'] for w in words[max(0, i - 4):i + len(target) + 4])
            print(f'start {s:.2f}  end {e:.2f}  ({fmt_ts(s)})   ...{ctx}...')
            hits += 1
    if not hits:
        print('no exact match. Try fewer words (whisper may have spelled something differently).')


if __name__ == '__main__':
    main()
