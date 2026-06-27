import sys
import os
import json
import importlib

sys.path.insert(0, os.path.dirname(__file__))

from backend.config.config import COMPANIES
from scrapers.utils import save_output


def _save_company_meta(companies: list) -> None:
    data_dir = os.path.join(os.path.dirname(__file__), "public", "data")
    os.makedirs(data_dir, exist_ok=True)
    meta = {
        c["company"]["name"]: c["company"].get("image", "")
        for c in companies
        if c.get("company", {}).get("name")
    }
    path = os.path.join(data_dir, "companies.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"  Company meta saved → {path}")


def _load_scraper(scraper_key: str):
    """Return the scrape_company function for the given key."""
    if "." in scraper_key:
        # custom.<module>  →  scrapers.custom.<module>
        module_path = f"scrapers.custom.{scraper_key.split('.', 1)[1]}"
    else:
        # built-in platform  →  scrapers.<platform>
        module_path = f"scrapers.{scraper_key}"

    try:
        mod = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        raise SystemExit(f"[ERROR] Cannot find scraper module '{module_path}': {e}")

    if not hasattr(mod, "scrape_company"):
        raise SystemExit(
            f"[ERROR] '{module_path}' has no scrape_company() function."
        )
    return mod.scrape_company


if __name__ == "__main__":
    _save_company_meta(COMPANIES)
    combined: list = []

    for company in COMPANIES:
        scraper_key = company.get("scraper")
        if not scraper_key:
            print(f"[SKIP] '{company.get('name')}' has no 'scraper' key — skipping")
            continue

        scrape_fn = _load_scraper(scraper_key)

        try:
            jobs = scrape_fn(company)
        except Exception as e:
            print(f"\n[ERROR] {company['name']}: {e}")
            jobs = []

        # Merge: replace any stale entries for this company, add fresh ones
        combined = [j for j in combined if j.get("company") != company["name"]]
        combined.extend(jobs)

        save_output(combined)
        print(f"  Frontend updated — {len(combined)} total jobs so far")

    print(f"\n{'=' * 60}")
    print(f"  Done: {len(combined)} jobs across {len(COMPANIES)} companies")
    print(f"{'=' * 60}")
