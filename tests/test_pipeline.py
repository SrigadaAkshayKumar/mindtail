import json
import shutil
from pathlib import Path

import pytest

from mindtail import captions, stock
from mindtail.spec import SpecError, load, parse

MINIMAL = {
    "id": "MT-9999",
    "title": "test",
    "status": "SCRIPT_DRAFT",
    "scenes": [
        {"duration": 1.0, "footage": {"query": "ocean"},
         "text": [{"content": "ये TEST है\nदूसरी line", "highlight": ["TEST"], "animation": "words"}]},
        {"duration": 1.5, "footage": {"file": "missing.mp4"}, "transition": "flash",
         "text": [{"content": "PART 2", "style": "tag", "start": 0.2, "end": 1.0}]},
    ],
}


def spec_from(data, tmp_path):
    return parse(data, tmp_path / "spec.yaml")


def test_parse_and_timing(tmp_path):
    s = spec_from(MINIMAL, tmp_path)
    assert s.duration == 2.5
    assert s.scene_starts() == [0.0, 1.0]
    assert s.scenes[0].text[0].end == 1.0  # defaults to scene end


def test_validation_collects_all_errors(tmp_path):
    bad = {"id": "", "status": "NOPE", "scenes": [
        {"duration": 1, "footage": {}, "motion": "spin",
         "text": [{"content": "x", "start": 0.8, "end": 0.5}],
         "sfx": [{"file": "a.wav", "at": 3}]}]}
    with pytest.raises(SpecError) as e:
        spec_from(bad, tmp_path)
    msg = str(e.value)
    for needle in ("`id` is required", "`status`", "`motion`", "give a `file` or a stock `query`",
                   "must be after", "past the scene duration"):
        assert needle in msg


def test_ass_output(tmp_path):
    ass = captions.build_ass(spec_from(MINIMAL, tmp_path))
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    lines = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    assert len(lines) == 2
    first = lines[0]
    assert first.startswith("Dialogue: 0,0:00:00.00,0:00:01.00,caption")
    assert "\\N" in first                                   # line break kept
    assert "\\fnNoto Sans}TEST" in first                    # Latin font switch
    assert captions.HIGHLIGHT["cyan"] in first              # highlight applied
    assert "\\t(0,80,\\alpha&H00&)" in first                # word reveal
    assert lines[1].startswith("Dialogue: 0,0:00:01.20,0:00:02.00,tag")


def test_ass_escapes_override_braces(tmp_path):
    data = json.loads(json.dumps(MINIMAL))
    data["scenes"][0]["text"][0]["content"] = "a {\\b1} b"
    ass = captions.build_ass(spec_from(data, tmp_path))
    first = [l for l in ass.splitlines() if l.startswith("Dialogue:")][0]
    assert "\\b1" not in first and "{/" not in first and "(/" in first


PEXELS = {"videos": [
    {"id": 1, "url": "https://www.pexels.com/video/1/", "duration": 3, "user": {"name": "A", "url": "u"},
     "video_files": [{"link": "l1", "width": 1080, "height": 1920, "file_type": "video/mp4"}]},
    {"id": 2, "url": "https://www.pexels.com/video/2/", "duration": 12, "user": {"name": "B", "url": "u"},
     "video_files": [{"link": "small", "width": 720, "height": 1280, "file_type": "video/mp4"},
                     {"link": "hd", "width": 1080, "height": 1920, "file_type": "video/mp4"},
                     {"link": "4k", "width": 2160, "height": 3840, "file_type": "video/mp4"}]},
]}


def test_stock_selection():
    c = stock.normalize_pexels(PEXELS)
    assert [x["download"] for x in c] == ["l1", "hd"]       # smallest file that is >= 1920 tall
    assert stock.choose(c, 0, 5.0, set())["id"] == "2"     # long enough clip preferred
    assert stock.choose(c, 0, 1.0, {"pexels-1"})["id"] == "2"  # no duplicate clips in a short


def test_pixabay_prefers_portrait():
    data = {"hits": [
        {"id": 5, "pageURL": "p5", "user": "x", "user_id": 1, "duration": 9,
         "videos": {"large": {"url": "land", "width": 1920, "height": 1080}}},
        {"id": 6, "pageURL": "p6", "user": "y", "user_id": 2, "duration": 9,
         "videos": {"large": {"url": "port", "width": 1080, "height": 1920}}},
    ]}
    assert [x["id"] for x in stock.normalize_pixabay(data)] == ["6", "5"]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_placeholder_render(tmp_path):
    from mindtail import qc
    from mindtail.render import render
    d = tmp_path / "MT-9999-test"
    d.mkdir()
    (d / "spec.yaml").write_text(json.dumps(MINIMAL), encoding="utf-8")
    out, warnings = render(load(d), placeholder=True, preview=True)
    assert out.exists()
    assert any("placeholder" in w for w in warnings)
    results = {c.name: c for c in qc.analyze(out)}
    assert results["resolution"].status == "PASS"
    assert abs(float(results["duration"].detail.rstrip("s").split("s")[0]) - 2.5) < 0.1
