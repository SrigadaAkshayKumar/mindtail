# MINDTAIL

Production workspace for **MINDTAIL** (@MIND_TAIL_99): faceless Hindi/Hinglish
YouTube **Shorts** made from stock B-roll, animated text, background music and
sound effects, with a Hindi AI voiceover to be added later.

The core of the repo is a small Python + ffmpeg pipeline. You describe a Short
in a `spec.yaml` (scenes, footage, text, music, sound effects) and the pipeline
downloads the footage, edits it to 1080×1920, animates the text, mixes the
audio to a consistent loudness and runs technical quality checks.

> `docs/MINDTAIL_BLUEPRINT.md` is the original brief. Where we have since
> changed direction (general content, B-roll style, no tagline), see
> `docs/DECISIONS.md`, which takes precedence.

## Setup

Needs **Python 3.10+** and **ffmpeg 5+ built with libass** (most builds are).

```bash
pip install -r requirements.txt
```

```bash
cp .env.example .env
```

Then put your free Pexels and Pixabay API keys in `.env`. Fonts are bundled
in `assets/fonts` (Noto Sans and Noto Sans Devanagari, SIL Open Font License).

## Try it

```bash
python -m mindtail samples
```

```bash
python -m mindtail render shorts/MT-0000-pipeline-demo --placeholder
```

This creates synthetic test media, renders the demo Short to
`shorts/MT-0000-pipeline-demo/render/MT-0000.mp4` and prints the QC report.
The demo's last scene uses a stock search; with keys in `.env`, run
`python -m mindtail fetch shorts/MT-0000-pipeline-demo` first and drop
`--placeholder`.

## Making a Short

| Step | Command / file |
|---|---|
| 1. Pick an idea | `ideas/backlog.md` |
| 2. Create its folder | `python -m mindtail new MT-0001 phone-habit --title "..."` |
| 3. Research (factual topics) | `shorts/MT-0001-*/research.md` |
| 4. Write the script | `shorts/MT-0001-*/script.md` → **your approval** |
| 5. Build the edit | `shorts/MT-0001-*/spec.yaml` ([format](docs/spec-reference.md)) |
| 6. Get footage | `python -m mindtail fetch shorts/MT-0001-*` |
| 7. Check media | `python -m mindtail check shorts/MT-0001-*` |
| 8. Quick preview | `python -m mindtail render shorts/MT-0001-* --preview` |
| 9. Final render + QC | `python -m mindtail render shorts/MT-0001-*` → **your approval** |
| 10. Credits & metadata | `python -m mindtail credits shorts/MT-0001-*`, `metadata.md` → **your approval to publish** |
| 11. Track results | `analytics/tracker.csv` |

`python -m mindtail status` lists every Short and its stage.
Full checklist: [docs/production-checklist.md](docs/production-checklist.md).

## Layout

```text
mindtail/            pipeline code (python -m mindtail ...)
shorts/MT-XXXX-slug/ one folder per Short: spec, script, research, metadata,
                     assets.lock.json (footage provenance); build/ and render/ are git-ignored
templates/           files copied into each new Short, plus idea and QC templates
library/             local media: footage/, music/, sfx/ (git-ignored)
assets/fonts/        bundled OFL fonts
brand/               brand guidelines, logo, banner
ideas/               backlog and research notes
analytics/           performance tracker
docs/                blueprint, decisions, spec reference, checklists
tests/               pytest suite (python -m pytest)
```

## Ground rules

- Nothing is published or scheduled without explicit approval.
- API keys live only in `.env`, which is never committed.
- Facts must be sourced in `research.md`. No invented statistics, studies or quotes.
- Footage comes from Pexels or Pixabay through the API, so each clip's source
  page, author and licence name are recorded automatically. Music and sound
  effects must come from sources whose licence allows YouTube use; record them
  under `credits:` in the spec.
