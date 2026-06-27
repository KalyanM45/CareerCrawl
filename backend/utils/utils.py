"""
Shared utilities used by every platform scraper:
  strip_html, HTTP headers, constants, LLM enrichment,
  title blacklist, job cache, blacklist, sort + output.
"""

import os
import re
import csv
import json
from datetime import datetime, timezone

from .llm import call_llm
from ..prompts.job_enrich import JOB_ENRICH_PROMPT

# ── Paths ─────────────────────────────────────────────────────────────
# __file__ is scrapers/utils.py  →  .. is the project root
DATA_DIR         = os.path.join(os.path.dirname(__file__), '..', 'public', 'data')
CACHE_DIR        = os.path.join(DATA_DIR, 'cache')
BLACKLIST_PATH   = os.path.join(CACHE_DIR, 'blacklist.json')

# ── Tuning ────────────────────────────────────────────────────────────
BATCH_SIZE    = 20
JD_WORKERS    = 8
JD_DELAY      = 0.15
PAGE_DELAY    = 0.4
MAX_RETRIES   = 4
JOB_LLM_BATCH = 5
JOB_LLM_DELAY = 1.5

# ── HTTP headers ──────────────────────────────────────────────────────
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
POST_HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}
GET_HEADERS  = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}


# ── HTML stripper ─────────────────────────────────────────────────────

def strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    for ent, ch in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                    ("&gt;", ">"), ("&#39;", "'"), ("&quot;", '"')]:
        text = text.replace(ent, ch)
    return re.sub(r"\s+", " ", text).strip()


# ── Title-based non-tech pre-filter ───────────────────────────────────

_TITLE_BLACKLIST_RE = re.compile(
    r'\b('
    r'ct technolog|mri technolog|radiol|radiograph'
    r'|surgical tech|scrub tech'
    r'|pharmacy tech|pharmacist'
    r'|lab tech|laboratory tech|medical lab|med lab'
    r'|sterile processing|central supply tech'
    r'|respiratory ther|cardiac tech|echo tech|ekg tech'
    r'|patient care tech|patient transport|transport tech'
    r'|phlebotom'
    r'|nuclear med'
    r'|ultrasound tech|sonograph'
    r'|mammograph'
    r'|perfusionist'
    r'|histotech|histolog'
    r'|polysomnograph'
    r'|nurse|nursing|rn |lpn |cna |caregiver|care aide'
    r'|physician|doctor|surgeon|therapist|therapy'
    r'|medical assist|clinical assist'
    r'|paramedic|emt '
    r'|dietitian|nutritionist'
    r'|social worker|case manager'
    r'|chaplain|chaplaincy'
    r'|housekeeper|housekeeping|environmental services'
    r'|food service|dietary aide|cook |chef '
    r'|security guard|security officer'
    r'|valet|parking'
    r')',
    re.IGNORECASE,
)

def _is_obviously_non_tech(job: dict) -> tuple[bool, str]:
    if _TITLE_BLACKLIST_RE.search(job.get("title", "")):
        return True, "Title pattern match: non-tech medical/clinical/facilities role"
    return False, ""


# ── LLM job-level enrichment ──────────────────────────────────────────

def _llm_enrich_jobs(jobs: list) -> dict:
    job_inputs = [
        {
            "job_id":     job["job_id"],
            "title":      job["title"],
            "department": job.get("department", ""),
            "location":   job.get("location", ""),
            "jd_snippet": (job.get("job_description") or "")[:1200],
        }
        for job in jobs
    ]

    result = call_llm(
        system_prompt=JOB_ENRICH_PROMPT,
        human_template=(
            "Classify and enrich these {count} job(s):\n\n{jobs_json}\n\n"
            "Return ONLY the JSON object keyed by job_id."
        ),
        variables={
            "count":     len(jobs),
            "jobs_json": json.dumps(job_inputs, ensure_ascii=False),
        },
    )  # prompt lives in src/prompts/job_enrich.py

    output = {}
    for job in jobs:
        jid  = job["job_id"]
        data = result.get(jid, {}) if isinstance(result, dict) else {}
        output[jid] = {
            "is_tech":    bool(data.get("is_tech", True)),
            "reason":     data.get("reason", ""),
            "location":   data.get("location") or None,
            "experience": data.get("experience") or None,
            "work_mode":  data.get("work_mode") or None,
        }
    return output


# ── Blacklist ─────────────────────────────────────────────────────────

def load_blacklist() -> dict:
    if os.path.exists(BLACKLIST_PATH):
        with open(BLACKLIST_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_blacklist(bl: dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(BLACKLIST_PATH, "w", encoding="utf-8") as f:
        json.dump(bl, f, ensure_ascii=False, indent=2)


# ── Per-company job cache ─────────────────────────────────────────────

def load_cache(company_id: str) -> dict:
    path = os.path.join(CACHE_DIR, f"{company_id}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_cache(company_id: str, cache: dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{company_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# ── Shared enrichment loop (same logic for every platform) ────────────

def run_llm_enrichment(new_jobs: list, blacklist: dict) -> tuple[list, dict]:
    """
    Run title pre-filter + LLM enrichment on new_jobs.
    Returns (kept_jobs, newly_blacklisted).
    Mutates kept jobs in-place (adds experience, may update location/remote_type).
    """
    from datetime import datetime, timezone

    newly_blacklisted: dict = {}
    llm_candidates   : list = []

    for job in new_jobs:
        blocked, reason = _is_obviously_non_tech(job)
        if blocked:
            jid = job["job_id"]
            newly_blacklisted[jid] = {
                "title":          job["title"],
                "company":        job["company"],
                "reason":         reason,
                "blacklisted_at": datetime.now(timezone.utc).isoformat(),
            }
            print(f"    [SKIP*] {jid:<22} {job['title'][:45]}  — {reason}")
        else:
            llm_candidates.append(job)

    if newly_blacklisted:
        print(f"  Pre-filter: {len(newly_blacklisted)} obvious non-tech job(s) removed")

    if llm_candidates:
        print(f"\n  LLM enriching {len(llm_candidates)} job(s) "
              f"in batches of {JOB_LLM_BATCH} ...")
        import time
        for i in range(0, len(llm_candidates), JOB_LLM_BATCH):
            batch = llm_candidates[i : i + JOB_LLM_BATCH]
            try:
                enriched = _llm_enrich_jobs(batch)
                for job in batch:
                    jid  = job["job_id"]
                    data = enriched.get(jid, {"is_tech": True})
                    if not data.get("is_tech", True):
                        newly_blacklisted[jid] = {
                            "title":          job["title"],
                            "company":        job["company"],
                            "reason":         data.get("reason", ""),
                            "blacklisted_at": datetime.now(timezone.utc).isoformat(),
                        }
                        print(f"    [SKIP] {jid:<22} {job['title'][:45]}"
                              f"  — {data.get('reason','')[:35]}")
                    else:
                        if data.get("location"):
                            job["location"] = data["location"]
                        job["experience"] = data.get("experience") or ""
                        if data.get("work_mode") and not job.get("remote_type"):
                            job["remote_type"] = data["work_mode"]
                        print(f"    [KEEP] {jid:<22} {job['title'][:45]}"
                              f"  exp={job.get('experience') or '-'}")
            except Exception as e:
                print(f"  ⚠  LLM failed for batch {i // JOB_LLM_BATCH + 1}: {e}"
                      f" — keeping all {len(batch)} job(s)")
                for job in batch:
                    job.setdefault("experience", "")
            time.sleep(JOB_LLM_DELAY)

    if newly_blacklisted:
        blacklist.update(newly_blacklisted)
        save_blacklist(blacklist)
        print(f"\n  Blacklisted {len(newly_blacklisted)} non-tech job(s) "
              f"— saved to blacklist.json")

    kept = [j for j in new_jobs if j["job_id"] not in newly_blacklisted]
    return kept, newly_blacklisted


# ── Sort + combined output ────────────────────────────────────────────

def sort_key(job: dict):
    from datetime import timedelta
    sd = job.get("start_date", "")
    if sd:
        try:
            return datetime.strptime(sd, "%Y-%m-%d")
        except ValueError:
            pass
    raw   = job.get("posted_date", "").lower()
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if "today"     in raw: return today
    if "yesterday" in raw: return today - timedelta(days=1)
    m = re.search(r"(\d+)\+?\s*day",   raw)
    if m: return today - timedelta(days=int(m.group(1)))
    m = re.search(r"(\d+)\+?\s*week",  raw)
    if m: return today - timedelta(weeks=int(m.group(1)))
    m = re.search(r"(\d+)\+?\s*month", raw)
    if m: return today - timedelta(days=int(m.group(1)) * 30)
    return datetime.min


def save_output(jobs: list) -> None:
    """Sort all jobs and write jobs.json + jobs.csv."""
    jobs.sort(key=sort_key, reverse=True)
    os.makedirs(DATA_DIR, exist_ok=True)

    json_path = os.path.join(DATA_DIR, "jobs.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved {len(jobs)} jobs → {json_path}")

    csv_path = os.path.join(DATA_DIR, "jobs.csv")
    fields   = ["job_id", "company", "company_image", "title", "location",
                "department", "posted_date", "start_date", "end_date",
                "time_left", "remote_type", "experience", "employment_type",
                "external_url", "job_description"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(jobs)
    print(f"  Saved {len(jobs)} jobs → {csv_path}")
