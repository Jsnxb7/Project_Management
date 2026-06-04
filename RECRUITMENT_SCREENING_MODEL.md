# Recruitment Screening Model

This project now includes a standalone recruitment screening model in:

```text
services/recruitment_screening_model.py
```

The model is intentionally separate from the Flask route layer. This makes it easier to test now and wire into the UI, background workers, or MongoDB workflow later.

## Purpose

The model screens applicants against a job description using the approach discussed for the AI-HRMS recruitment module:

1. Extract JD keywords and important skill phrases.
2. Extract resume text from PDF, DOCX, DOC, or TXT.
3. Convert JD and resume text into vector form.
4. Calculate cosine similarity.
5. Calculate keyword coverage.
6. Evaluate resume writing style and grammar-like quality.
7. Evaluate resume structure quality.
8. Calculate a weighted final score.
9. Shortlist only applicants who cross the minimum score threshold.
10. Return matched keywords and highlighted snippets for the report.

## Main files

```text
services/recruitment_screening_model.py     # Main model
services/ai_recruitment_service.py          # Backwards-compatible wrapper
scripts/demo_recruitment_screening.py       # Standalone test/demo script
```

## Default scoring formula

```text
Final Score =
  Semantic Similarity Score × 55%
+ Keyword Coverage Score × 25%
+ Writing Quality Score × 12%
+ Resume Structure Score × 8%
```

These weights are configurable through `ScreeningConfig`.

## Main classes

### `ScreeningConfig`

Controls model behavior:

```python
ScreeningConfig(
    semantic_weight=0.55,
    keyword_weight=0.25,
    writing_weight=0.12,
    structure_weight=0.08,
    minimum_score=70.0,
    keyword_limit=45,
    use_sentence_transformer=False,
)
```

### `ApplicantInput`

A clean input structure for batch screening:

```python
ApplicantInput(
    candidate_name="Aman Sharma",
    candidate_email="aman@example.com",
    resume_text="...",
    resume_path=None,
)
```

### `RecruitmentScreeningModel`

Main model class.

Important methods:

```python
extract_keywords(jd_text)
extract_resume_text(path)
screen_resume(jd_text, resume_text, jd_keywords=None, min_score=70)
rank_applicants(jd_text, applicants, min_score=70, shortlisted_only=True)
evaluate_answer(question, expected_answer, candidate_answer)
```

## Example usage

```python
from services.recruitment_screening_model import ApplicantInput, RecruitmentScreeningModel

jd = """
Python Flask Developer required with Python, Flask, MongoDB,
REST API, Git, authentication, dashboard development, and AI embeddings.
"""

applicants = [
    ApplicantInput(
        candidate_name="Aman Sharma",
        candidate_email="aman@example.com",
        resume_text="""
        Skills: Python, Flask, MongoDB, REST API, Git.
        Built an HRMS dashboard with authentication and AI resume screening.
        """,
    )
]

model = RecruitmentScreeningModel()
result = model.rank_applicants(jd, applicants, min_score=70)
print(result["visible_candidates"])
```

## Example output

```json
{
  "candidate_name": "Aman Sharma",
  "final_score": 84.38,
  "recommendation": "Shortlist",
  "matched_keywords": ["python", "flask", "mongodb", "rest api", "git"]
}
```

## Report fields returned by the model

Each candidate report includes:

```text
candidate_name
semantic_score
keyword_score
writing_score
structure_score
final_score
minimum_score
recommendation
confidence
matched_keywords
missing_keywords
matched_keyword_details
highlighted_snippets
score_breakdown
summary
```

## Highlight support

The model returns `highlighted_snippets`, where matched keywords are wrapped in:

```html
<mark>matched keyword</mark>
```

This can be displayed directly in the recruitment report UI later.

## Optional transformer embedding upgrade

By default, the model uses a lightweight offline embedding method so the app runs without downloading large models.

Later, install `sentence-transformers` and enable:

```python
from services.recruitment_screening_model import RecruitmentScreeningModel, ScreeningConfig

model = RecruitmentScreeningModel(
    ScreeningConfig(
        use_sentence_transformer=True,
        sentence_transformer_model="sentence-transformers/all-MiniLM-L6-v2"
    )
)
```

This keeps the current model lightweight while allowing a stronger semantic embedding backend later.

## Demo command

Run this from the project root:

```bash
python scripts/demo_recruitment_screening.py
```

The demo prints extracted JD keywords and screening results for sample applicants.

## Next wiring steps

Later, this model can be wired to:

1. Job creation page: extract and save JD keywords.
2. Application page: extract resume text and call `screen_resume`.
3. Applications dashboard: show only candidates above the threshold by default.
4. Candidate report page: show score breakdown, matched/missing keywords, and highlighted snippets.
5. Background workers: move screening into Celery for high-volume recruitment.
