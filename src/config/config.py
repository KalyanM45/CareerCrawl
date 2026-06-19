COMPANIES = [
    {
        "id": "ascendion",
        "scraper":  "eightfold",
        "company": {
            "name": "Ascendion",
            "domain": "https://ascendion.com",
            "image": "assets/images/companies/ascendion.png"
            },
        "links": {
            "base_url": "https://jobs.ascendion.com",
            "job_list_url": "https://jobs.ascendion.com/api/pcsx/search?domain=ascendion.com&query=&location=India&start=",
            "job_main_url": "https://jobs.ascendion.com/api/pcsx/position_details?position_id={JOB_ID}&domain=ascendion.com",
        },
        "others": {
        }
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
