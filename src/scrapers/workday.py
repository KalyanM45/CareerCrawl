"""
Workday platform scraper.

Required company config keys:
    id, name, image,
    jobs_page   – full URL of the public jobs board (used to seed cookies)
    portal_base – e.g. https://company.wd5.myworkdayjobs.com
    board_path  – e.g. /en-US/Careers
    api_url     – full POST endpoint for job listings
    detail_base – base for per-job GET detail calls

Called by main.py as:  scrape_company(company_dict) → list[job_dict]
"""

import os
import re
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

import requests

from ..utils.utils import (
    strip_html,
    BROWSER_HEADERS, POST_HEADERS, GET_HEADERS,
    CACHE_DIR, BATCH_SIZE, JD_WORKERS, JD_DELAY, PAGE_DELAY, MAX_RETRIES,
    GROQ_API_KEY, GROQ_MODEL,
    _is_obviously_non_tech, run_llm_enrichment,
    load_blacklist, load_cache, save_cache,
)

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

FACET_CACHE_PATH = os.path.join(CACHE_DIR, 'facets_cache.json')


# ── Session ───────────────────────────────────────────────────────────

def _build_session(jobs_page: str) -> requests.Session:
    s = requests.Session()
    s.headers.update(BROWSER_HEADERS)
    try:
        s.get(jobs_page, timeout=30)
    except Exception:
        pass
    return s

def _make_worker_session(cookies: dict) -> requests.Session:
    s = requests.Session()
    s.headers.update(BROWSER_HEADERS)
    s.cookies.update(cookies)
    return s


# ── Facet cache ───────────────────────────────────────────────────────

def _load_facet_cache() -> dict:
    if os.path.exists(FACET_CACHE_PATH):
        with open(FACET_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}

def _save_facet_cache(cache: dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(FACET_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# ── Department LLM classifier (Workday-specific) ──────────────────────

_DEPT_SYSTEM_PROMPT = """\
You are an expert job market analyst. Your job is to classify company department \
names from a Workday career portal and decide whether each one is TECHNOLOGY or \
DATA related.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CLASSIFY AS TECH (is_tech = true) IF the department primarily involves:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Software / application development, engineering, architecture
• Data work of any kind: analytics, data science, data engineering,
  business intelligence, reporting, visualization, ETL, modeling,
  statistical analysis, quantitative research
• Information Technology (IT): systems administration, infrastructure,
  cloud computing, DevOps, SRE, networking, databases, cybersecurity
• Digital products or digital transformation
• Machine learning, AI, NLP, computer vision
• Product management (typically for tech products)
• UX / UI design and research
• Technical program / project management
• Computational research, bioinformatics, cheminformatics
• Data strategy, technology strategy, innovation labs

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CLASSIFY AS NOT TECH (is_tech = false) IF the department is primarily:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Finance, Accounting, Treasury, FP&A
• Legal, Compliance, Regulatory Affairs, Intellectual Property
• Human Resources, Talent Acquisition, Recruiting, L&D
• Marketing, Communications, Brand, PR, Advertising
• Sales, Business Development, Account Management, Revenue
• Customer Service, Customer Success, Customer Experience
• Medical Affairs, Clinical Operations, Pharmacovigilance
• Regulatory Affairs, Drug Safety, Clinical Data Management
• Scientific Affairs (wet-lab / non-computational science)
• Manufacturing, Quality, Supply Chain, Logistics, Operations
• Strategy / Consulting (UNLESS explicitly data or technology strategy)
• Administrative, Facilities, Real Estate, EHS
• Procurement, Vendor Management

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AMBIGUOUS CASES — apply these rules strictly:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• "Research" alone          → false UNLESS "Quantitative Research", "Computational Research"
• "Operations" alone        → false UNLESS "Technology Operations", "Data Operations"
• "Strategy" alone          → false UNLESS "Data Strategy", "Technology Strategy"
• "Product" alone           → true  (assume tech product management)
• "Innovation"              → true  (assume tech/digital innovation)
• Company-specific acronyms → false if meaning is unclear
• "Rotational Program"      → false

RULES:
1. Classify EVERY department in the input — never skip one.
2. Use the EXACT department name from the input — no rewording.
3. When in doubt, classify as TRUE — job-level LLM pass will filter non-tech postings.
4. Provide a brief, specific reason for each decision.

Respond ONLY with valid JSON — no extra text:
{{"classifications": [{{"name": "<exact dept name>", "is_tech": true, "reason": "<one sentence>"}}]}}
"""

def _llm_classify_depts(names: list[str]) -> list[dict]:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set")

    numbered = "\n".join(f"{i+1}. {n}" for i, n in enumerate(names))
    prompt = ChatPromptTemplate.from_messages([
        ("system", _DEPT_SYSTEM_PROMPT),
        ("human",
         "Classify each of the following {count} department(s).\n\n"
         "{departments}\n\nReturn ONLY the JSON object."),
    ])
    llm   = ChatGroq(api_key=GROQ_API_KEY, model=GROQ_MODEL, temperature=0)
    chain = prompt | llm | JsonOutputParser()
    result = chain.invoke({"count": len(names), "departments": numbered})
    rows   = result.get("classifications", [])

    name_set  = set(names)
    seen      = set()
    validated = []
    for row in rows:
        n = row.get("name", "")
        if n in name_set and n not in seen:
            seen.add(n)
            validated.append({
                "name":    n,
                "is_tech": bool(row.get("is_tech", False)),
                "reason":  row.get("reason", ""),
            })
    for n in names:
        if n not in seen:
            validated.append({"name": n, "is_tech": False,
                               "reason": "Not returned by LLM — defaulting to non-tech"})
    return validated


# ── Facet probe ───────────────────────────────────────────────────────

_DEPT_FACET_KW = ["jobfamily", "jobcategor", "jobfunction", "department",
                   "jobtitle", "worktype", "jobgroup", "jobtype"]
_SKIP_FACET_KW = ["location", "region", "state", "province", "country",
                   "city", "timetype", "time_type", "remote", "posting"]

def _probe_facets(company: dict, session: requests.Session) -> Optional[tuple]:
    try:
        r = session.post(
            company["api_url"], headers=POST_HEADERS,
            json={"limit": 1, "offset": 0, "searchText": "", "appliedFacets": {}},
            timeout=30,
        )
        r.raise_for_status()
        facets = r.json().get("facets", [])
    except Exception as e:
        print(f"  ⚠  Facet probe failed: {e}")
        return None

    if not facets:
        return None

    for facet in facets:
        pl = facet.get("facetParameter", "").lower()
        if any(kw in pl for kw in _DEPT_FACET_KW) and facet.get("values"):
            return facet["facetParameter"], facet["values"]

    candidates = [
        f for f in facets
        if f.get("values") and not any(
            kw in f.get("facetParameter", "").lower() for kw in _SKIP_FACET_KW
        )
    ]
    if not candidates:
        candidates = facets
    best = max(candidates, key=lambda f: len(f.get("values", [])), default=None)
    return (best["facetParameter"], best["values"]) if best and best.get("values") else None


def _fetch_tech_facets(company: dict, session: requests.Session) -> Optional[dict]:
    """
    Returns {"facetParam": ["id1", ...]} for tech departments, or None to skip company.
    Classifies new departments via LLM; reuses cached decisions for known ones.
    """
    cid   = company["id"]
    probe = _probe_facets(company, session)
    if probe is None:
        print("  ⚠  Could not probe facets — skipping company")
        return None

    facet_param, api_values = probe
    current: dict[str, str] = {v["descriptor"]: v["id"] for v in api_values}

    facet_cache  = _load_facet_cache()
    stored_entry = facet_cache.get(cid, {})
    stored_cats  = {c["name"]: c for c in stored_entry.get("categories", [])}

    new_names = sorted(set(current) - set(stored_cats))
    removed   = sorted(set(stored_cats) - set(current))

    newly_classified = []
    if new_names:
        print(f"  {len(new_names)} new department(s) → asking LLM ...")
        try:
            newly_classified = _llm_classify_depts(new_names)
            for r in newly_classified:
                mark = "✓" if r["is_tech"] else "✗"
                print(f"    [NEW] {mark}  {r['name']}")
                print(f"           ↳ {r['reason']}")
        except Exception as e:
            print(f"  ⚠  LLM failed ({e}) — new depts marked non-tech")
            newly_classified = [
                {"name": n, "is_tech": False, "reason": "LLM unavailable"}
                for n in new_names
            ]
    else:
        print("  No new departments — reusing cached classifications")

    new_by_name = {r["name"]: r for r in newly_classified}
    all_cats    = []

    for name, fid in current.items():
        if name in stored_cats:
            cat = dict(stored_cats[name])
            cat["id"]     = fid
            cat["active"] = True
        else:
            r   = new_by_name[name]
            cat = {"name": name, "id": fid,
                   "is_tech": r["is_tech"], "reason": r["reason"], "active": True}
        all_cats.append(cat)

    for name in removed:
        cat = dict(stored_cats[name])
        cat["active"] = False
        all_cats.append(cat)

    facet_cache[cid] = {
        "facet_param":  facet_param,
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "categories":   all_cats,
    }
    _save_facet_cache(facet_cache)

    print(f"\n  Department classification for '{company['name']}' "
          f"(facet: {facet_param}):")
    print(f"  {'DEPT':<45} {'TECH?':<7} REASON")
    print(f"  {'-'*45} {'-'*6} {'-'*30}")
    for cat in sorted(all_cats, key=lambda c: c["name"]):
        status = "REMOVED" if not cat["active"] else ("YES" if cat["is_tech"] else "no")
        print(f"  {cat['name']:<45} {status:<7} {cat.get('reason','')[:50]}")

    tech_ids = [
        cat["id"] for cat in all_cats
        if cat.get("is_tech") and cat.get("active")
    ]
    if not tech_ids:
        print(f"\n  ✗ No tech departments — {company['name']} will be SKIPPED\n")
        return None

    print(f"\n  → {len(tech_ids)} tech department(s) selected\n")
    return {facet_param: tech_ids}


# ── Listing + JD fetchers ─────────────────────────────────────────────

def _extract_job_id(external_path: str) -> str:
    m = re.search(r'_([A-Za-z]{0,3}\d+)(?:-\d+)?$', external_path)
    return m.group(1) if m else external_path

def _fetch_listings(company: dict, session: requests.Session,
                    applied_facets: dict) -> list:
    all_listings = []
    offset       = 0
    total_cap    = None

    while True:
        payload = {"limit": BATCH_SIZE, "offset": offset,
                   "searchText": "", "appliedFacets": applied_facets}
        resp = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                r = session.post(company["api_url"], headers=POST_HEADERS,
                                 json=payload, timeout=30)
                if r.status_code in (429, 502, 503):
                    wait = 2 ** attempt
                    print(f"  ⚠  HTTP {r.status_code} at offset {offset} "
                          f"— retry {attempt}/{MAX_RETRIES} in {wait}s ...")
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                resp = r
                break
            except requests.exceptions.RequestException as e:
                wait = 2 ** attempt
                print(f"  ⚠  Error at offset {offset}: {e} "
                      f"— retry {attempt}/{MAX_RETRIES} in {wait}s ...")
                time.sleep(wait)

        if resp is None:
            print(f"  ✗ Giving up at offset {offset} after {MAX_RETRIES} retries")
            break

        data     = resp.json()
        postings = data.get("jobPostings", [])
        if not postings:
            break

        reported = data.get("total", 0)
        if reported > 0:
            total_cap = reported

        for job in postings:
            ext    = job.get("externalPath", "")
            job_id = _extract_job_id(ext)
            all_listings.append({
                "job_id":          job_id,
                "company":         company["name"],
                "company_image":   company.get("image", ""),
                "title":           job.get("title", ""),
                "location":        job.get("locationsText", ""),
                "department":      job.get("jobCategoryLabel", ""),
                "posted_date":     job.get("postedOn", ""),
                "start_date":      "",
                "end_date":        "",
                "time_left":       "",
                "remote_type":     "",
                "employment_type": job.get("timeType", ""),
                "external_url":    company["portal_base"] + company["board_path"] + ext,
                "_ext":            ext,
                "job_description": "",
                "experience":      "",
            })

        offset += BATCH_SIZE
        print(f"  Listed {len(all_listings)}/{total_cap or '?'} ...")
        if total_cap and offset >= total_cap:
            break
        time.sleep(PAGE_DELAY)

    return all_listings

def _fetch_jd(detail_base: str, ext: str, cookies: dict) -> dict:
    time.sleep(JD_DELAY)
    s = _make_worker_session(cookies)
    try:
        resp = s.get(f"{detail_base}{ext}", headers=GET_HEADERS, timeout=30)
        resp.raise_for_status()
        info = resp.json().get("jobPostingInfo", {})
        return {
            "job_id":          info.get("jobReqId", ""),
            "start_date":      info.get("startDate", ""),
            "end_date":        info.get("endDate", ""),
            "time_left":       info.get("timeLeftToApply", ""),
            "remote_type":     info.get("remoteType", ""),
            "job_description": strip_html(info.get("jobDescription", "")),
        }
    except Exception:
        return {"job_id": "", "start_date": "", "end_date": "",
                "time_left": "", "remote_type": "", "job_description": ""}


# ── Main company scraper ──────────────────────────────────────────────

def scrape_company(company: dict) -> list:
    cid  = company["id"]
    name = company["name"]

    print(f"\n{'=' * 60}")
    print(f"  {name}  [Workday]")
    print(f"{'=' * 60}")

    cache     = load_cache(cid)
    blacklist = load_blacklist()
    print(f"  Cache: {len(cache)} existing jobs | Blacklist: {len(blacklist)} blocked IDs")

    session     = _build_session(company["jobs_page"])
    tech_facets = _fetch_tech_facets(company, session)
    if tech_facets is None:
        return []

    listings = _fetch_listings(company, session, tech_facets)
    live_ids = {j["job_id"] for j in listings if j["job_id"]}

    new_jobs      = [j for j in listings
                     if j["job_id"] not in cache and j["job_id"] not in blacklist]
    removed       = [jid for jid in cache if jid not in live_ids]
    n_blacklisted = sum(1 for j in listings if j["job_id"] in blacklist)

    print(f"\n  + {len(new_jobs):>4} new"
          f"   ~ {len(listings) - len(new_jobs) - n_blacklisted:>4} unchanged"
          f"   - {len(removed):>4} removed"
          f"   x {n_blacklisted:>4} blacklisted (skipped)\n")

    # Fetch JDs in parallel
    if new_jobs:
        print(f"  Fetching {len(new_jobs)} new JDs with {JD_WORKERS} workers ...\n")
        cookies    = dict(session.cookies)
        print_lock = threading.Lock()
        done       = [0]
        with ThreadPoolExecutor(max_workers=JD_WORKERS) as pool:
            future_map = {
                pool.submit(_fetch_jd, company["detail_base"], job["_ext"], cookies): job
                for job in new_jobs
            }
            for future in as_completed(future_map):
                job = future_map[future]
                try:
                    detail = future.result()
                    if detail["job_id"]:
                        job["job_id"] = detail["job_id"]
                    for k in ("start_date", "end_date", "time_left",
                               "remote_type", "job_description"):
                        job[k] = detail[k]
                except Exception:
                    pass
                with print_lock:
                    done[0] += 1
                    print(f"    [{done[0]:>3}/{len(new_jobs)}]"
                          f"  {job['job_id'] or '?':>10}  {job['title']}")

    # LLM enrichment
    new_jobs, _ = run_llm_enrichment(new_jobs, blacklist)

    # Update cache
    for jid in removed:
        del cache[jid]

    for job in new_jobs:
        job.pop("_ext", None)
        job.setdefault("experience", "")
        cache[job["job_id"]] = job

    new_ids = {j["job_id"] for j in new_jobs}
    for j in listings:
        jid = j["job_id"]
        if jid not in cache or jid in new_ids:
            continue
        preserved = {k: cache[jid].get(k, "") for k in
                     ("job_id", "start_date", "end_date", "time_left",
                      "remote_type", "job_description", "experience")}
        cache[jid] = {k: v for k, v in j.items() if k != "_ext"}
        cache[jid].update(preserved)

    save_cache(cid, cache)
    print(f"\n  Cache saved — {len(cache)} active jobs for {name}")
    return list(cache.values())
