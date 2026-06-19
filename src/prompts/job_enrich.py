from pathlib import Path

JOB_ENRICH_PROMPT = (Path(__file__).parent / "job_enrich.md").read_text(encoding="utf-8")
