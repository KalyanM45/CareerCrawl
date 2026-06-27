

class CompanyConfig:
    
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
            "others": {}
        },
]
