from pathlib import Path

DB_PATH = Path("jobs.db")
CSV_PATH = Path("jobs.csv")
TABLE = "jobs"
RELEVANT_TABLE = "relevant_jobs"

# Jobs scoring at or above this (0-100) are saved to the relevant_jobs table
RELEVANCE_THRESHOLD = 70
# Levels are ordered lowest to highest; Jev's score is the (fractional) level index
RELEVANCE_CRITERIA = [
    "The candidate's background is in a different field; almost none of the "
    "required skills or experience appear in the resume",
    "Some overlapping skills, but the candidate is missing most core required "
    "skills or falls well short of the required years of experience",
    "The candidate meets roughly half of the required qualifications; notable "
    "gaps in core skills or experience level",
    "The candidate meets most required qualifications and the experience "
    "level, with only minor gaps or missing nice-to-haves",
    "The candidate meets all required qualifications and the experience "
    "level, and also matches several of the preferred qualifications",
]

OLLAMA_MODEL = "qwen3:8b"
DISTILL_PROMPT = """\
You condense job descriptions down to the candidate requirements only.

Keep:
- Years of experience (overall and per skill/technology, exactly as stated)
- Required / minimum qualifications
- Preferred / nice-to-have qualifications
- Technical skills, languages, frameworks, tools, and platforms
- Education, certifications, and work authorization/clearance requirements

Remove: company overview, mission/culture text, salary, benefits, perks, \
location/hybrid details, application instructions, and EEO statements.

Rules:
- Use only information in the description. Never invent or infer requirements.
- Keep the original wording for skills and numbers; drop filler words.
- Omit a section entirely if the description has nothing for it.
- Output plain text in exactly this format, with no preamble or closing remarks:

Experience: <years of experience, or "Not specified">
Required:
- <requirement>
Preferred:
- <requirement>
Skills: <comma-separated list>
"""
