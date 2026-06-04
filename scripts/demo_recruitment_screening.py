"""Small standalone demo for the recruitment screening model.

Run from the project root:
    python scripts/demo_recruitment_screening.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.recruitment_screening_model import ApplicantInput, RecruitmentScreeningModel

JD = """
Python Flask Developer required. The candidate must know Python, Flask, MongoDB,
REST APIs, Git, authentication, dashboard development, and deployment basics.
Experience with AI modules, embeddings, and HRMS workflows is preferred.
"""

APPLICANTS = [
    ApplicantInput(
        candidate_name="Aman Sharma",
        candidate_email="aman@example.com",
        resume_text="""
        Aman Sharma | aman@example.com | +91 9999999999
        Skills: Python, Flask, MongoDB, REST API, Git, HTML, CSS, JavaScript.
        Projects: Built an HRMS dashboard using Flask and MongoDB. Implemented
        authentication, employee records, attendance reports, and AI resume screening.
        Deployed Flask applications with Gunicorn and Git.
        """,
    ),
    ApplicantInput(
        candidate_name="Riya Mehta",
        candidate_email="riya@example.com",
        resume_text="""
        Riya Mehta | riya@example.com
        Skills: Excel, communication, payroll operations, hiring coordination.
        Experience: Managed HR documentation and candidate calls. Basic knowledge of Python.
        """,
    ),
]

if __name__ == "__main__":
    model = RecruitmentScreeningModel()
    result = model.rank_applicants(JD, APPLICANTS, min_score=70, shortlisted_only=False)
    print("Extracted JD keywords:", result["jd_keywords"][:15])
    for row in result["full_reports"]:
        print("-", row["candidate_name"], row["final_score"], row["recommendation"], row["matched_keywords"][:8])
