# Decisions log

Newest first. These override `MINDTAIL_BLUEPRINT.md` where they differ.

## 2026-11-10: Direction after kickoff

| Topic | Decision |
|---|---|
| Format | YouTube **Shorts only**, no long-form. |
| Content | **General youth content**, not only dark stories. Topics: shocking-but-true and mind-blowing facts, mind/psychology, stories & mysteries, motivation & life lessons, modern life & social media, relatable youth topics (college, friends, phones, career pressure). |
| Style | Fast-paced editing built from **stock B-roll**, light **text animations**, and careful **music + sound-effect mixing** (the most important craft element). |
| Voice | **Hindi AI voiceover**. Provider, plan and settings to be discussed later; the pipeline already supports a voice track with automatic music ducking. |
| Tagline | **None.** "Every Mind Has a Dark Story" is dropped. Channel name stays MINDTAIL. |
| Editing stack | **Automated with code**: Python + ffmpeg (this repo). |
| Footage source | **Free libraries**: Pexels and Pixabay via their APIs (keys in `.env`). |
| Music / SFX source | Free libraries whose licence permits YouTube use (e.g. YouTube Audio Library, Pixabay). Downloaded manually into `library/`, credited in each spec. |
| Repo | `SrigadaAkshayKumar/mindtail`, first commit pushed to `main` at the creator's request. |

### Still open

- Voiceover provider/model/voice, and how voice files are produced.
- Logo and banner refresh without the tagline.
- Upload schedule and cadence.
- Whether to use the YouTube API for uploads (would remain approval-gated).
- Caption/subtitle styling beyond the current defaults, after the first real Shorts.

### Environment note

The cloud session that built this repo cannot reach the Pexels and Pixabay
APIs (network policy), so `fetch` was tested with recorded sample responses
only. It needs a real run with your keys before the first production Short.
