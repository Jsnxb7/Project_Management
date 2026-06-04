"""
Backwards-compatible recruitment AI service.

The Flask routes can keep importing these functions, while the actual model is
implemented in services/recruitment_screening_model.py. Later, this layer can be
replaced with a Celery worker, Hugging Face endpoint, or separate AI microservice
without changing the route code.
"""

from pathlib import Path
from typing import Optional, Sequence

from services.recruitment_screening_model import (
    ApplicantInput,
    RecruitmentScreeningModel,
    ScreeningConfig,
    get_default_screening_model,
)


def clean_text(text):
    return get_default_screening_model().clean_text(text)


def tokenize(text):
    return get_default_screening_model().tokenize(text)


def extract_keywords(text, limit=35):
    return get_default_screening_model().extract_keywords(text, limit=limit)


def embed_text(text):
    return get_default_screening_model().embed_text(text)


def cosine_similarity(vec_a, vec_b):
    return round(get_default_screening_model().cosine_similarity(vec_a, vec_b), 4)


def keyword_match(jd_keywords, resume_text):
    return get_default_screening_model().keyword_match(jd_keywords, resume_text)


def grammar_score(text):
    return get_default_screening_model().writing_quality_score(text)


def extract_resume_text(path):
    return get_default_screening_model().extract_resume_text(Path(path))


def screen_resume(jd_text, resume_text, jd_keywords=None, min_score=70, candidate_name=None):
    return get_default_screening_model().screen_resume(
        jd_text=jd_text,
        resume_text=resume_text,
        jd_keywords=jd_keywords,
        min_score=min_score,
        candidate_name=candidate_name,
    )


def rank_applicants(jd_text, applicants, jd_keywords=None, min_score=70, shortlisted_only=True):
    return get_default_screening_model().rank_applicants(
        jd_text=jd_text,
        applicants=applicants,
        jd_keywords=jd_keywords,
        min_score=min_score,
        shortlisted_only=shortlisted_only,
    )


def build_report_summary(final, matched, missing, writing):
    return get_default_screening_model().build_report_summary(
        final=final,
        minimum=70,
        matched=matched,
        missing=missing,
        writing=writing,
        structure=0,
    )


def evaluate_answer(question, expected_answer, candidate_answer, keywords=None):
    return get_default_screening_model().evaluate_answer(
        question=question,
        expected_answer=expected_answer,
        candidate_answer=candidate_answer,
        keywords=keywords,
    )
