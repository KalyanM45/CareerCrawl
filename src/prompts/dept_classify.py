from pathlib import Path

DEPT_SYSTEM_PROMPT = (Path(__file__).parent / "dept_classify.md").read_text(encoding="utf-8")
