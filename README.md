# Job Search Automation Script

A small Python script that finds new job postings, trims each description down to just its requirements, and scores how well your resume matches. It is meant to run on a schedule so the best-fitting roles are waiting for you whenever you check.

## What it does

Each run of `main.py`:

1. **Scrapes** recent postings from Indeed and LinkedIn using [JobSpy](https://github.com/speedyapply/JobSpy).
2. **Skips** jobs it has already seen, using the job URL as the key.
3. **Distills** each new description with a local [Ollama](https://ollama.com) model (`qwen3:8b`). The result keeps only the experience, required and preferred qualifications, and skills.
4. **Scores** your resume against each distilled description from 0 to 100 using [TypeSafe AI](https://typesafe.ai) ([Python SDK docs](https://docs.typesafe.ai/sdk/python/)).
5. **Saves** jobs scoring at or above `RELEVANCE_THRESHOLD` (default 70) to a separate "relevant" table.

The search term, location, sites, and time window are set in the `scrape_jobs(...)` call in `main()`. The model, prompt, scoring rubric, and threshold are in `config.py`.

## How the data is stored

Everything is stored locally in the project folder. Both data files are git-ignored.

| Location | Contents |
| --- | --- |
| `jobs.db` → `jobs` table | Every scraped job: all JobSpy columns plus `distilled_description`. Has a unique index on `job_url`. |
| `jobs.db` → `relevant_jobs` table | Jobs at or above the relevance threshold, with their `relevance_score`. |
| `jobs.csv` | A CSV copy of the `jobs` table, appended on each run, for easy viewing in a spreadsheet. |

## Credits

This project is built on top of **[JobSpy](https://github.com/speedyapply/JobSpy)** by speedyapply. JobSpy handles the hard part: scraping LinkedIn, Indeed, Glassdoor, Google, ZipRecruiter and more through one `scrape_jobs()` call, and returning clean, consistent data as a pandas DataFrame. Without it, this project would need a custom scraper for every job board, plus the upkeep of keeping each one working. Huge thanks to the JobSpy maintainers and contributors for an amazing library. If it helps you too, please consider [starring the repo](https://github.com/speedyapply/JobSpy).

Relevance scoring is powered the system 1 classifier [Jev by TypeSafe AI](https://typesafe.ai).

## Setup

**Prerequisites:**

- [uv](https://docs.astral.sh/uv/)
- [Ollama](https://ollama.com), with the model pulled: `ollama pull qwen3:8b`
- A [TypeSafe AI](https://typesafe.ai) API key

### 1. Clone the project

```bash
git clone https://github.com/Ramasubramanian99/job_search_script.git
cd job_search_script
uv sync
```

### 2. Add a `resume.py` file

Create `resume.py` in the project root with your resume as plain text in a `RESUME` string. The file is git-ignored, so your personal details stay off GitHub. If `RESUME` is empty, the pipeline still scrapes and distills jobs but skips relevance scoring.

```python
RESUME = """
Summary: Full stack developer with 5 years of experience in Python (Django, FastAPI)
and JavaScript (React, TypeScript).

Skills: Python, JavaScript, TypeScript, React, Django, FastAPI, PostgreSQL, Docker, AWS

Experience:
Corp, Toronto, Ontario
Software Developer, May 2022 – Present
- Built an internal inventory platform in React and Django used by 200+ staff
- Automated reporting with Python, cutting manual effort by 60%

Education:
BSc in Computer Science, University of Toronto, 2018 – 2022
"""
```

### 3. Add your TypeSafe AI API key

Create a `.env` file in the project root. It is git-ignored and loaded automatically by `main.py`.

```
TYPESAFE_API_KEY=your-key-here
```

### 4. Schedule it to run automatically

Before scheduling, run it once by hand to check that everything works:

```bash
uv run main.py
```

By default it fetches jobs posted in the last 12 hours (`hours_old=12`), so run it at least every 12 hours to avoid gaps. The steps below use every 6 hours. Use the full path to `uv` (from `which uv` or `where uv`) because scheduled tasks don't load your shell's `PATH`.

**macOS / Linux (cron):** run `crontab -e` and add:

```cron
0 */6 * * * cd /path/to/job_search_script && /path/to/uv run main.py >> pipeline.log 2>&1
```

**Windows (Task Scheduler):** run this in PowerShell:

```powershell
$action  = New-ScheduledTaskAction -Execute "C:\path\to\uv.exe" -Argument "run main.py" -WorkingDirectory "C:\path\to\job_search_script"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 6)
Register-ScheduledTask -TaskName "JobAutomationPipeline" -Action $action -Trigger $trigger
```

Ollama must be running when the task fires.

## Functions

Listed in the order they run:

1. **`main()`**: The entry point. It scrapes jobs with JobSpy's `scrape_jobs()`, then runs the filter, distill, save, and score steps below in order.
2. **`filter_new_jobs(jobs)`**: Removes duplicate URLs and converts non-numeric columns to text so SQLite can store them. Returns only the jobs not already in the database.
3. **`get_existing_urls(conn)`**: Returns the set of `job_url`s already in the `jobs` table, or an empty set on the first run before the table exists.
4. **`distill_descriptions(jobs)`**: Loops over the new jobs, distills each description, and adds the results as a `distilled_description` column.
5. **`distill_description(description)`**: Sends one job description to the local Ollama model with `DISTILL_PROMPT`. Returns a short summary of the experience, qualifications, and skills, with thinking turned off.
6. **`save_jobs(jobs)`**: Appends the new jobs to the `jobs` table in `jobs.db` and to `jobs.csv`, and makes sure there's a unique index on `job_url`.
7. **`ensure_distilled_column(conn)`**: A migration helper. Adds the `distilled_description` column to a database or CSV created before that column existed.
8. **`score_relevance(client, distilled_description)`**: Asks TypeSafe AI to grade your resume against a job's requirements using the five-level `RELEVANCE_CRITERIA` rubric. Returns the result as a 0–100 score.
9. **`save_relevant_jobs(jobs)`**: Appends jobs scoring at or above `RELEVANCE_THRESHOLD` to the `relevant_jobs` table, with a unique index on `job_url`.
