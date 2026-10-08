import csv
import sqlite3
from pathlib import Path

import ollama
import pandas as pd
from jobspy import scrape_jobs

DB_PATH = Path("jobs.db")
CSV_PATH = Path("jobs.csv")
TABLE = "jobs"

OLLAMA_MODEL = "qwen3:8b"
# TODO: fill in the distillation instructions
DISTILL_PROMPT = ""


def get_existing_urls(conn: sqlite3.Connection) -> set[str]:
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)
    ).fetchone()
    if not table_exists:
        return set()
    return {row[0] for row in conn.execute(f"SELECT job_url FROM {TABLE}")}


def ensure_distilled_column(conn: sqlite3.Connection) -> None:
    """Add distilled_description to a DB/CSV created before the column existed."""
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")}
    if columns and "distilled_description" not in columns:
        conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN distilled_description TEXT")

    if CSV_PATH.exists():
        existing_csv = pd.read_csv(CSV_PATH)
        if "distilled_description" not in existing_csv.columns:
            existing_csv["distilled_description"] = None
            existing_csv.to_csv(
                CSV_PATH, index=False, quoting=csv.QUOTE_NONNUMERIC, escapechar="\\"
            )


def filter_new_jobs(jobs: pd.DataFrame) -> pd.DataFrame:
    jobs = jobs.drop_duplicates(subset="job_url")
    # SQLite can't store dates/lists directly, so store everything non-numeric as text
    jobs = jobs.astype({c: str for c in jobs.select_dtypes(exclude="number").columns})
    jobs = jobs.replace({"None": None, "nan": None, "NaT": None})

    with sqlite3.connect(DB_PATH) as conn:
        existing = get_existing_urls(conn)
    return jobs[~jobs["job_url"].isin(existing)].copy()


def distill_description(description: str | None) -> str | None:
    if not description:
        return None
    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": DISTILL_PROMPT},
            {"role": "user", "content": description},
        ],
        think=False,  # skip qwen3's reasoning output, we only want the answer
    )
    return response.message.content.strip()


def distill_descriptions(jobs: pd.DataFrame) -> pd.DataFrame:
    distilled = []
    for i, description in enumerate(jobs["description"], start=1):
        print(f"Distilling description {i}/{len(jobs)}")
        distilled.append(distill_description(description))
    jobs["distilled_description"] = distilled
    return jobs


def save_jobs(jobs: pd.DataFrame) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        ensure_distilled_column(conn)
        jobs.to_sql(TABLE, conn, if_exists="append", index=False)
        conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS idx_job_url ON {TABLE}(job_url)")

    jobs.to_csv(
        CSV_PATH,
        mode="a",
        header=not CSV_PATH.exists(),
        index=False,
        quoting=csv.QUOTE_NONNUMERIC,
        escapechar="\\",
    )


def main():
    print("Hello from job-automation-pipeline!")
    jobs = scrape_jobs(
        site_name=["indeed", "linkedin"],
        search_term="software engineer",
        location="Toronto, ON",
        results_wanted=5,
        job_type=["fulltime", "contract"],
        hours_old=12,
        country_indeed='canada',
        fetch_description=True 
        # proxies=["208.195.175.46:65095", "208.195.175.45:65095", "localhost"],
    )
    print(f"Found {len(jobs)} jobs")

    new_jobs = filter_new_jobs(jobs)
    print(f"{len(new_jobs)} new jobs ({len(jobs) - len(new_jobs)} already stored)")
    if new_jobs.empty:
        return

    new_jobs = distill_descriptions(new_jobs)
    save_jobs(new_jobs)
    print(f"Saved {len(new_jobs)} new jobs")


if __name__ == "__main__":
    main()
