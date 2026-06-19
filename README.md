# CareerCrawl

CareerCrawl is a scraper that crawls job listings directly from company career portals — Workday and Eightfold.ai — and uses an LLM to automatically filter out every non-tech role before saving anything. Instead of browsing ten different career pages and manually skipping irrelevant postings, you point CareerCrawl at a list of companies and get back a clean, deduplicated feed of software, data, and engineering jobs in `jobs.json` and `jobs.csv`.

Each run fetches only what is new. Existing jobs are loaded from a per-company cache so the LLM never sees the same listing twice. Jobs that are classified as non-tech — like a "CT Technologist" that slips through a tech department filter — are permanently blacklisted so they never surface again. The result is a feed that gets cleaner over time, not noisier.

The LLM pipeline runs in two passes. For Workday portals, it first classifies all available departments and queries only the tech ones, which drastically reduces the number of irrelevant listings fetched. Every new job then goes through a job-level enrichment pass that confirms whether the role is genuinely tech, extracts required experience, and resolves the work mode. A regex pre-filter catches obvious medical and clinical titles before they even reach the LLM, saving API calls.

---

## Installation

**Requirements:** Python 3.11+ and a [Groq API key](https://console.groq.com/) (free tier is enough).

```bash
git clone https://github.com/KalyanM45/OpenRoles.git
cd OpenRoles
```

Install dependencies with `uv` (recommended):

```bash
uv sync
```

Or with pip:

```bash
pip install -r requirements.txt
```

Create your environment file:

```bash
cp .env.example .env
```

Open `.env` and fill in your Groq key:

```env
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.1-8b-instant
```
---

## Running

```bash
python main.py
```

CareerCrawl processes each company in order, prints a live count of new, unchanged, removed, and blacklisted jobs, and writes the combined output after every company so the file is always up to date even if the run is interrupted.

Output is written to:

```
public/data/jobs.json   ← full feed sorted newest-first
public/data/jobs.csv    ← same data as CSV
```

Each job includes the title, company, location, department, posted date, experience requirement, work mode (Remote / Hybrid / On-site), employment type, a link to the original posting, and the full job description with HTML stripped.

---

## License

MIT
