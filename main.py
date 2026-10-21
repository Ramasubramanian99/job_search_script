import csv
import sqlite3

import ollama
import pandas as pd
from dotenv import load_dotenv
from jobspy import scrape_jobs
from typesafe_sdk import Score, TypeSafeClient

from config import (
    CSV_PATH,
    DB_PATH,
    DISTILL_PROMPT,
    OLLAMA_MODEL,
    RELEVANCE_CRITERIA,
    RELEVANCE_THRESHOLD,
    RELEVANT_TABLE,
    TABLE,
)
from resume import RESUME

# Load TYPESAFE_API_KEY (and any other secrets) from .env
load_dotenv()


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
            {"role": "user", "content": f"{description}\n\n/no_think"},
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


def score_relevance(client: TypeSafeClient, distilled_description: str | None) -> float | None:
    """Score how well the resume fits a job's requirements on a 0-100 scale using Jev."""
    if not distilled_description:
        return None
    response = client.system_one(
        state={"resume": RESUME, "job_requirements": distilled_description},
        questions={
            "relevance": Score(
                instructions="How well does the candidate's resume match the job requirements?",
                criteria=RELEVANCE_CRITERIA,
            ),
        },
    )
    score = response.answers["relevance"].score
    return round(score / (len(RELEVANCE_CRITERIA) - 1) * 100, 1)


def save_relevant_jobs(jobs: pd.DataFrame) -> None:
    # Only called with jobs new to the jobs table, so they can't already be here
    with sqlite3.connect(DB_PATH) as conn:
        jobs.to_sql(RELEVANT_TABLE, conn, if_exists="append", index=False)
        conn.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS idx_relevant_job_url ON {RELEVANT_TABLE}(job_url)"
        )


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

    if not RESUME:
        print("RESUME is empty, skipping relevance scoring")
        return

    with TypeSafeClient() as client:
        scores = []
        for i, distilled in enumerate(new_jobs["distilled_description"], start=1):
            score = score_relevance(client, distilled)
            print(f"Scored job {i}/{len(new_jobs)}: {score}")
            scores.append(score)
    new_jobs["relevance_score"] = pd.to_numeric(scores)

    relevant_jobs = new_jobs[new_jobs["relevance_score"] >= RELEVANCE_THRESHOLD]
    if not relevant_jobs.empty:
        save_relevant_jobs(relevant_jobs)
    print(f"Saved {len(relevant_jobs)} relevant jobs (score >= {RELEVANCE_THRESHOLD})")


if __name__ == "__main__":
    main()
