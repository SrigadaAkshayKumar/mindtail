# Production checklist (per Short)

Approval gates are marked **[APPROVAL]**. Nothing goes public without the last one.

## 1. Idea
- [ ] Idea in `ideas/backlog.md` with topic, hook and why it will hold attention
- [ ] Not harmful, not misinformation, not a stereotype
- [ ] **[APPROVAL]** Idea selected (can be approved in batches)

## 2. Research (facts, "shocking" claims, real events)
- [ ] Every claim in `research.md` with source URL, date checked, confidence
- [ ] Disputed or unverified points removed or clearly labelled
- [ ] Fiction or dramatisation labelled as such

## 3. Script
- [ ] 3+ hook options, best one chosen
- [ ] One idea; every line moves it forward; no padding
- [ ] Natural spoken Hindi/Hinglish, read aloud once
- [ ] Hook's promise is paid off
- [ ] **[APPROVAL]** Script approved

## 4. Edit plan (`spec.yaml`)
- [ ] A visual change every 1.5-3 s; a footage query that matches each beat
- [ ] Key words highlighted, not whole sentences
- [ ] Sound effects on cuts and reveals; music chosen for the mood
- [ ] Music/SFX licence allows YouTube use, recorded under `credits`
- [ ] `python -m mindtail check` passes

## 5. Assets
- [ ] `fetch` done; every clip looked at (relevant, no logos/watermarks/identifiable private people in a misleading context)
- [ ] Voiceover (when added) listened to in full; pronunciation fixed
- [ ] **[APPROVAL]** Voice and visual assets approved

## 6. Render & QC
- [ ] `render --preview` reviewed; timing adjusted
- [ ] Final `render`; automatic QC has no FAIL
- [ ] Watched in full on a phone: text readable, nothing under the Shorts UI, audio balanced, no glitches
- [ ] Complete `templates/qc-checklist.md` in the Short's folder
- [ ] **[APPROVAL]** Final render approved

## 7. Package
- [ ] 3-5 title options, description, a few relevant hashtags (`metadata.md`)
- [ ] `python -m mindtail credits` output added to the description where useful
- [ ] Altered/synthetic content disclosure decided
- [ ] **[APPROVAL]** Public upload/schedule approved

## 8. After publishing
- [ ] URL, date and title recorded in `metadata.md`; status `PUBLISHED`
- [ ] Metrics added to `analytics/tracker.csv` at 24 h, 7 d, 28 d
