import csv
import sqlite3
from pathlib import Path

import pandas as pd
from jobspy import scrape_jobs

DB_PATH = Path("jobs.db")
CSV_PATH = Path("jobs.csv")
TABLE = "jobs"


def get_existing_urls(conn: sqlite3.Connection) -> set[str]:
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)
    ).fetchone()
    if not table_exists:
        return set()
    return {row[0] for row in conn.execute(f"SELECT job_url FROM {TABLE}")}


def save_new_jobs(jobs: pd.DataFrame) -> pd.DataFrame:
    jobs = jobs.drop_duplicates(subset="job_url")
    # SQLite can't store dates/lists directly, so store everything non-numeric as text
    jobs = jobs.astype({c: str for c in jobs.select_dtypes(exclude="number").columns})
    jobs = jobs.replace({"None": None, "nan": None, "NaT": None})

    with sqlite3.connect(DB_PATH) as conn:
        existing = get_existing_urls(conn)
        new_jobs = jobs[~jobs["job_url"].isin(existing)]
        if new_jobs.empty:
            return new_jobs

        new_jobs.to_sql(TABLE, conn, if_exists="append", index=False)
        conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS idx_job_url ON {TABLE}(job_url)")

    new_jobs.to_csv(
        CSV_PATH,
        mode="a",
        header=not CSV_PATH.exists(),
        index=False,
        quoting=csv.QUOTE_NONNUMERIC,
        escapechar="\\",
    )
    return new_jobs


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

    new_jobs = save_new_jobs(jobs)
    print(f"Saved {len(new_jobs)} new jobs ({len(jobs) - len(new_jobs)} already stored)")


if __name__ == "__main__":
    main()
