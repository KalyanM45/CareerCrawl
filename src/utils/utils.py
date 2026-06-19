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

from dotenv import load_dotenv
load_dotenv()

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

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

# ── Groq ──────────────────────────────────────────────────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL   = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

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

_JOB_ENRICH_PROMPT = """\
You are a highly skilled software engineer / data scientist with a CS or IT degree.
You are browsing job postings and deciding which ones are worth applying for.

THE CORE TEST — ask this single question:
  "Would I — a skilled CS/IT-educated person — consider applying for this job
   based on my software, data, or engineering background?"

  YES → is_tech = true
  NO  → is_tech = false

Examples of the mindset:
  • Software Engineer at Pfizer → YES (I write code, my background fits)
  • Data Scientist at Merck → YES (ML/stats, my background fits)
  • CT Technologist at a hospital → NO (needs medical/ARRT training, not CS)
  • Clinical Data Manager at a pharma company → NO (needs clinical trial knowledge, not coding)
  • Transportation Tech at a hospital → NO (patient transport, nothing to do with CS)
  • Financial Analyst using Excel → NO (accounting/finance role, not tech)
  • HR Systems Admin managing Workday → NO (HR software admin, not engineering)

USING SOFTWARE AS A TOOL IN A NON-TECH JOB DOES NOT MAKE IT A TECH ROLE.
The question is: does MY CS/IT BACKGROUND give me a real advantage in this role?

INCLUDE (is_tech = true) — the job IS the technology:
  • Software / backend / frontend / full-stack / platform engineer
  • Data scientist, ML engineer, AI engineer, NLP, computer vision
  • Data analyst or business analyst who writes SQL/Python/R or builds
    BI dashboards as their PRIMARY output (not just uses Excel)
  • Data engineer, ETL/pipeline developer, data platform engineer
  • Cloud engineer, DevOps, SRE, infrastructure, network engineer
  • Cybersecurity / information security engineer or analyst
  • Product manager for a SOFTWARE or DATA product
  • Solutions architect, enterprise architect, technical architect
  • QA / SDET / test automation engineer (writes code to test code)
  • Technical consultant who DELIVERS data/tech implementations
    (builds models, integrates systems, writes code for clients)

EXCLUDE (is_tech = false) — uses technology but the JOB IS NOT TECHNOLOGY:

Medical / Clinical tech-adjacent (exclude ALL of these):
  • Clinical data manager / analyst managing trial data in EDC systems
    (Medidata, Veeva Vault, Oracle Clinical) — the job is clinical, not engineering
  • Pharmacovigilance / drug safety analyst using Argus, ARISg, or safety DBs
  • Regulatory affairs analyst using eCTD, dossier, or submission software
  • Medical affairs / medical information using clinical databases
  • Lab analyst / scientist using instrumentation or LIMS software
  • Clinical research associate / coordinator using CTMS or EDC tools
  • Healthcare "IT analyst" who configures or supports EHR/EMR (Epic, Cerner)
    without writing code — this is system admin / change management
  • Medical device role focused on V&V, IEC 62304 compliance, or QA of device SW
  • Bioinformatics technician running standard vendor pipelines (not building them)

Business-tool users (exclude):
  • Financial / FP&A analyst using Excel, SAP, Oracle Financials
  • HR / HRIS analyst administering Workday, SuccessFactors, or SAP HR
  • Sales ops / CRM analyst using Salesforce without customizing or coding it
  • Marketing / digital analyst using Google Analytics, Adobe, or ad platforms
  • Supply chain / procurement analyst using ERP systems

Pure non-tech (exclude):
  • Sales, account management, business development
  • Marketing, brand, PR, communications
  • HR, recruiting, L&D, benefits
  • Legal, compliance, regulatory (non-engineering)
  • Finance, accounting, treasury
  • Administrative, exec assistants, office management

CRITICAL — HEALTHCARE "TECH" / "TECHNOLOGIST" TRAP:
  In a hospital or healthcare company, "Tech" and "Technologist" almost always mean
  a MEDICAL TECHNICIAN, not a software/IT role. These are ALL false:
  • CT Technologist, MRI Technologist, Radiology Technologist → medical imaging tech
  • Surgical Technologist, Scrub Tech → operating room role
  • Pharmacy Technician / Pharmacy Tech → dispensing medication
  • Lab Technician / Lab Tech / Medical Laboratory Technologist → clinical lab work
  • Transportation Tech → patient transport in a hospital
  • Sterile Processing Technician → medical equipment sterilization
  • Respiratory Therapist / Cardiac Tech / Echo Tech → clinical care
  • OR Tech, ER Tech, Patient Care Tech → bedside / clinical roles
  If the word "Tech" or "Technologist" is in the title at a hospital/healthcare company,
  it is FALSE unless the JD explicitly requires a CS/IT/engineering degree or skills
  like writing code, managing servers, or building software systems.

AMBIGUOUS RULES:
  • "Analyst" → check JD. "Strong SQL/Python required" → TRUE.
    "Experience with Excel and clinical systems" → FALSE.
  • "Informatics" → TRUE if they write code or build pipelines.
    FALSE if they use clinical informatics tools (Epic, Cerner, lab systems).
  • "Data Manager" in pharma/biotech → almost always FALSE (clinical data mgmt).
  • "Consultant" → TRUE only if they BUILD or IMPLEMENT tech solutions.
  • When genuinely unsure → FALSE. This board shows only pure tech roles.

TASK 2 — FIELD EXTRACTION (do for ALL jobs):
  • location  : Primary work city/state from JD. Return null if not found.
  • experience: Required experience e.g. "3-5 years", "5+ years". Null if absent.
  • work_mode : One of "Remote", "Hybrid", "On-site", or null.

Input: JSON array — each item has job_id, title, department, location, jd_snippet.

Output — JSON object keyed by EXACT job_id from input:
{{"JR001": {{"is_tech": true,  "reason": "builds ML pipelines in Python/Spark", "location": "Austin, TX", "experience": "3+ years", "work_mode": "Hybrid"}},
 "JR002": {{"is_tech": false, "reason": "clinical data manager using EDC, not coding", "location": null, "experience": null, "work_mode": null}}}}

Return ONLY valid JSON. No markdown, no text outside the JSON object.
"""


def _llm_enrich_jobs(jobs: list) -> dict:
    """
    Classify each job as tech/non-tech and extract location, experience, work_mode.
    Returns dict keyed by job_id. Defaults is_tech=True for any job the LLM misses.
    """
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set")

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

    prompt = ChatPromptTemplate.from_messages([
        ("system", _JOB_ENRICH_PROMPT),
        ("human",
         "Classify and enrich these {count} job(s):\n\n{jobs_json}\n\n"
         "Return ONLY the JSON object keyed by job_id."),
    ])
    llm   = ChatGroq(api_key=GROQ_API_KEY, model=GROQ_MODEL, temperature=0)
    chain = prompt | llm | JsonOutputParser()

    result = chain.invoke({
        "count":     len(jobs),
        "jobs_json": json.dumps(job_inputs, ensure_ascii=False),
    })

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
