import time
import threading
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from ..utils.utils import (
    strip_html,
    BROWSER_HEADERS, GET_HEADERS,
    JD_WORKERS, JD_DELAY, PAGE_DELAY, MAX_RETRIES,
    _is_obviously_non_tech, run_llm_enrichment,
    load_blacklist, load_cache, save_cache,
)

PAGE_SIZE = 10

_WORK_MODE_MAP = {
    "remote":       "Remote",
    "remote_local": "Remote",
    "hybrid":       "Hybrid",
    "onsite":       "On-site",
    "client-site":  "On-site",
}

def _map_work_mode(raw: str | None) -> str:
    return _WORK_MODE_MAP.get((raw or "").lower(), "")

def _ts_to_iso(ts: int) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return ""


# ── Session ───────────────────────────────────────────────────────────

def _build_session(base_url: str) -> requests.Session:
    s = requests.Session()
    s.headers.update(BROWSER_HEADERS)
    try:
        s.get(f"{base_url}/careers", timeout=30)
    except Exception:
        pass
    return s


# ── Listing fetcher ───────────────────────────────────────────────────

def _fetch_listings(company: dict, session: requests.Session) -> list:
    all_listings = []
    start        = 0
    total        = None
    base_url     = company["links"]["base_url"]
    job_list_url = company["links"]["job_list_url"]
    name         = company["company"]["name"]
    image        = company["company"].get("image", "")

    while True:
        url = f"{job_list_url}{start}&sort_by=match&filter_include_remote=1"
        resp = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                r = session.get(url, headers=GET_HEADERS, timeout=30)
                if r.status_code in (429, 502, 503):
                    wait = 2 ** attempt
                    print(f"  ⚠  HTTP {r.status_code} at start={start} "
                          f"— retry {attempt}/{MAX_RETRIES} in {wait}s ...")
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                resp = r
                break
            except requests.exceptions.RequestException as e:
                wait = 2 ** attempt
                print(f"  ⚠  Error at start={start}: {e} "
                      f"— retry {attempt}/{MAX_RETRIES} in {wait}s ...")
                time.sleep(wait)

        if resp is None:
            print(f"  ✗ Giving up at start={start} after {MAX_RETRIES} retries")
            break

        data      = resp.json()
        positions = data.get("data", {}).get("positions", [])
        if not positions:
            break

        if total is None:
            total = data.get("data", {}).get("count", 0)

        for pos in positions:
            job_id = str(pos["id"])
            locs   = pos.get("locations") or []
            all_listings.append({
                "job_id":          job_id,
                "company":         name,
                "company_image":   image,
                "title":           pos.get("name", ""),
                "location":        ", ".join(locs),
                "department":      pos.get("department") or "",
                "posted_date":     "",
                "start_date":      "",
                "end_date":        "",
                "time_left":       "",
                "remote_type":     _map_work_mode(pos.get("workLocationOption")),
                "employment_type": "",
                "external_url":    base_url + (pos.get("positionUrl") or f"/careers/job/{job_id}"),
                "job_description": "",
                "experience":      "",
                "_posted_ts":      pos.get("postedTs", 0),
            })

        start += PAGE_SIZE
        print(f"  Listed {len(all_listings)}/{total or '?'} ...")
        if total and start >= total:
            break
        time.sleep(PAGE_DELAY)

    return all_listings


# ── JD fetcher ────────────────────────────────────────────────────────

def _fetch_jd(job_main_url: str, job_id: str, cookies: dict) -> dict:
    time.sleep(JD_DELAY)
    s = requests.Session()
    s.headers.update(BROWSER_HEADERS)
    s.cookies.update(cookies)
    try:
        url  = job_main_url.replace("{JOB_ID}", job_id)
        resp = s.get(url, headers=GET_HEADERS, timeout=30)
        resp.raise_for_status()
        d = resp.json()
        return {
            "job_description": strip_html(d.get("job_description", "")),
            "department":      d.get("department") or "",
            "remote_type":     _map_work_mode(d.get("work_location_option")),
        }
    except Exception:
        return {"job_description": "", "department": "", "remote_type": ""}


# ── Main company scraper ──────────────────────────────────────────────

def scrape_company(company: dict) -> list:
    cid  = company["id"]
    name = company["company"]["name"]

    print(f"\n{'=' * 60}")
    print(f"  {name}  [Eightfold]")
    print(f"{'=' * 60}")

    cache     = load_cache(cid)
    blacklist = load_blacklist()
    print(f"  Cache: {len(cache)} existing jobs | Blacklist: {len(blacklist)} blocked IDs")

    session  = _build_session(company["links"]["base_url"])
    listings = _fetch_listings(company, session)
    live_ids = {j["job_id"] for j in listings}

    new_jobs      = [j for j in listings
                     if j["job_id"] not in cache and j["job_id"] not in blacklist]
    removed       = [jid for jid in cache if jid not in live_ids]
    n_blacklisted = sum(1 for j in listings if j["job_id"] in blacklist)

    print(f"\n  + {len(new_jobs):>4} new"
          f"   ~ {len(listings) - len(new_jobs) - n_blacklisted:>4} unchanged"
          f"   - {len(removed):>4} removed"
          f"   x {n_blacklisted:>4} blacklisted (skipped)\n")

    if new_jobs:
        print(f"  Fetching {len(new_jobs)} new JDs with {JD_WORKERS} workers ...\n")
        cookies      = dict(session.cookies)
        job_main_url = company["links"]["job_main_url"]
        print_lock   = threading.Lock()
        done         = [0]

        with ThreadPoolExecutor(max_workers=JD_WORKERS) as pool:
            future_map = {
                pool.submit(_fetch_jd, job_main_url, job["job_id"], cookies): job
                for job in new_jobs
            }
            for future in as_completed(future_map):
                job = future_map[future]
                try:
                    detail = future.result()
                    job["job_description"] = detail["job_description"]
                    if detail["department"]:
                        job["department"] = detail["department"]
                    if detail["remote_type"] and not job["remote_type"]:
                        job["remote_type"] = detail["remote_type"]
                except Exception:
                    pass
                with print_lock:
                    done[0] += 1
                    print(f"    [{done[0]:>3}/{len(new_jobs)}]"
                          f"  {job['job_id']:>20}  {job['title']}")

    for job in new_jobs:
        iso = _ts_to_iso(job.pop("_posted_ts", 0))
        job["start_date"]  = iso
        job["posted_date"] = iso

    new_jobs, _ = run_llm_enrichment(new_jobs, blacklist)

    for jid in removed:
        del cache[jid]

    for job in new_jobs:
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
        cache[jid] = {k: v for k, v in j.items() if k != "_posted_ts"}
        cache[jid].update(preserved)

    save_cache(cid, cache)
    print(f"\n  Cache saved — {len(cache)} active jobs for {name}")
    return list(cache.values())
