# RunItBack — Written Summary (162 words)

**An estimated 63.5% of ML papers don't reproduce.** The bottleneck isn't compute — it's diagnosis. Reproducing a baseline usually means a week of setup, two days of training, and a four-point gap you can't explain. The bug — an augmentation leak, a train-test overlap, a metric mismatch, a missing `model.eval()` — was always a static read away.

RunItBack does the static read. Point it at a paper and a repo; four Opus 4.7 agents (Paper Analyst, Code & Data Auditor, Validator, Reviewer) running on Claude Managed Agents return a diagnostic report with a verdict, claim-by-claim verification, severity-ranked findings, and unified-diff fixes — in minutes, before any GPU starts.

Opus 4.7 ingests PDFs natively (tables, figures, equations — no OCR, no `pdftotext`), carries the full reproducibility-failure taxonomy across 60-turn tool-using sessions, and enforces a ≥ 2-agent cross-check rule that surfaces genuine disagreements instead of hallucinating consensus. Managed Agents gave us sandbox, tools, sessions, and streaming on day one — we wrote only the brain.
