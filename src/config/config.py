"""
Master company list. Every entry MUST include:
    id      – unique slug used for cache filename
    name    – display name
    image   – relative path shown in the UI
    scraper – which scraper to use:
                "workday"          → scrapers/workday.py
                "eightfold"        → scrapers/eightfold.py
                "custom.<module>"  → scrapers/custom/<module>.py

Each scraper expects its own platform-specific keys alongside those above.
"""

COMPANIES = [

    # ── Eightfold.ai ──────────────────────────────────────────────────
    # Keys: domain, base_url, location
    {
        "id":       "ascendion",
        "name":     "Ascendion",
        "image":    "assets/images/companies/ascendion.jpg",
        "scraper":  "eightfold",
        "domain":   "ascendion.com",
        "base_url": "https://jobs.ascendion.com",
        "location": "India",
    },

    # ── Workday ───────────────────────────────────────────────────────
    # Keys: jobs_page, portal_base, board_path, api_url, detail_base
    # {
    #     "id":          "example",
    #     "name":        "Example Corp",
    #     "image":       "assets/images/companies/example.jpg",
    #     "scraper":     "workday",
    #     "jobs_page":   "https://example.wd5.myworkdayjobs.com/en-US/Careers",
    #     "portal_base": "https://example.wd5.myworkdayjobs.com",
    #     "board_path":  "/en-US/Careers",
    #     "api_url":     "https://example.wd5.myworkdayjobs.com/wday/cxs/example/Careers/jobs",
    #     "detail_base": "https://example.wd5.myworkdayjobs.com/wday/cxs/example/Careers",
    # },

    # ── Custom (company-specific) ─────────────────────────────────────
    # Scraper lives in scrapers/custom/<module>.py
    # {
    #     "id":      "somecompany",
    #     "name":    "Some Company",
    #     "image":   "assets/images/companies/somecompany.jpg",
    #     "scraper": "custom.somecompany",
    #     # ...any keys the custom scraper needs
    # },

]
