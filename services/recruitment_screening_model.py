"""
Recruitment Screening Model
==========================

Standalone AI recruitment screening layer for AI PeopleOps HRMS.

This module is intentionally independent from Flask routes so it can be tested,
replaced, upgraded, or moved into a worker service later.

Core idea:
- Extract important keywords/phrases from the JD.
- Extract resume text from PDF/DOCX/TXT.
- Embed JD and resume text into vector form.
- Calculate cosine similarity.
- Score keyword coverage.
- Score writing style, grammar-like quality, and resume structure.
- Generate an explainable screening report with matched keyword highlights.
- Filter/rank candidates by a minimum score threshold.

The default embedding backend is lightweight and offline-friendly. If
sentence-transformers is installed and a model is available locally/online, the
class can use it by setting use_sentence_transformer=True.
"""

from __future__ import annotations

import hashlib
import html
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import PyPDF2
except Exception:  # optional dependency
    PyPDF2 = None

try:
    import docx
except Exception:  # optional dependency
    docx = None

try:
    from sentence_transformers import SentenceTransformer  # type: ignore
except Exception:  # optional dependency
    SentenceTransformer = None


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "by", "for", "from",
    "has", "have", "had", "in", "into", "is", "it", "its", "of", "on", "or", "that",
    "the", "their", "there", "these", "this", "to", "was", "were", "with", "will", "would",
    "you", "your", "we", "our", "they", "them", "he", "she", "his", "her", "role", "job",
    "candidate", "applicant", "profile", "work", "working", "required", "preferred", "must",
    "should", "good", "strong", "excellent", "ability", "responsible", "responsibilities",
    "know", "needs", "need", "basic", "basics", "using", "include", "includes", "developer",
    "experience", "experienced", "development", "deployment", "modules", "module", "workflow", "workflows",
}

# Expand this list as your project grows. These are boosted during extraction.
SKILL_HINTS = {
    "python", "flask", "django", "fastapi", "java", "spring", "node", "express", "react",
    "angular", "vue", "javascript", "typescript", "html", "css", "tailwind", "bootstrap",
    "mongodb", "mongo", "postgresql", "mysql", "sql", "redis", "celery", "rabbitmq",
    "docker", "kubernetes", "aws", "azure", "gcp", "linux", "nginx", "gunicorn", "git",
    "github", "gitlab", "rest", "api", "apis", "graphql", "microservices", "oauth", "jwt",
    "machine learning", "deep learning", "nlp", "ai", "rag", "llm", "transformers", "rest api", "rest apis",
    "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "opencv", "analytics",
    "hrms", "payroll", "attendance", "recruitment", "onboarding", "performance", "compliance",
    "communication", "leadership", "management", "stakeholder", "negotiation", "sourcing",
    "screening", "interviewing", "employee relations", "talent acquisition",
}

SECTION_HEADERS = {
    "skills", "technical skills", "experience", "work experience", "projects", "education",
    "certifications", "achievements", "summary", "objective", "responsibilities", "requirements",
    "preferred qualifications", "required qualifications",
}

ACTION_VERBS = {
    "built", "created", "developed", "designed", "implemented", "managed", "led", "optimized",
    "deployed", "integrated", "automated", "improved", "reduced", "increased", "analyzed",
}

COMMON_GRAMMAR_RED_FLAGS = {
    "i has", "i is", "we was", "they was", "responsible to", "worked on it project",
    "good in", "knowledge on", "having experience", "fresher candidate with good knowledge in",
}


@dataclass
class ScreeningConfig:
    semantic_weight: float = 0.55
    keyword_weight: float = 0.25
    writing_weight: float = 0.12
    structure_weight: float = 0.08
    minimum_score: float = 70.0
    keyword_limit: int = 45
    embedding_dimensions: int = 768
    use_sentence_transformer: bool = False
    sentence_transformer_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    def normalized_weights(self) -> Dict[str, float]:
        total = self.semantic_weight + self.keyword_weight + self.writing_weight + self.structure_weight
        if not total:
            return {"semantic": 0.55, "keyword": 0.25, "writing": 0.12, "structure": 0.08}
        return {
            "semantic": self.semantic_weight / total,
            "keyword": self.keyword_weight / total,
            "writing": self.writing_weight / total,
            "structure": self.structure_weight / total,
        }


@dataclass
class ApplicantInput:
    candidate_name: str
    resume_text: str = ""
    resume_path: Optional[str] = None
    candidate_email: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class RecruitmentScreeningModel:
    def __init__(self, config: Optional[ScreeningConfig] = None):
        self.config = config or ScreeningConfig()
        self._st_model = None
        if self.config.use_sentence_transformer and SentenceTransformer is not None:
            try:
                self._st_model = SentenceTransformer(self.config.sentence_transformer_model)
            except Exception:
                # Keep the app usable even if the transformer model cannot load.
                self._st_model = None

    # -----------------------------
    # Text extraction and cleaning
    # -----------------------------
    def clean_text(self, text: str) -> str:
        text = text or ""
        text = text.replace("\x00", " ")
        text = re.sub(r"[\t\r]+", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def tokenize(self, text: str) -> List[str]:
        raw = re.findall(r"[A-Za-z][A-Za-z0-9+#.\-]{1,}", text or "")
        return [t.lower().strip(".-") for t in raw if t.strip(".-")]

    def sentence_split(self, text: str) -> List[str]:
        chunks = re.split(r"(?<=[.!?])\s+|\n+", text or "")
        return [c.strip() for c in chunks if c and c.strip()]

    def extract_resume_text(self, path: str | Path) -> str:
        file_path = Path(path)
        suffix = file_path.suffix.lower()
        if suffix == ".pdf" and PyPDF2:
            pages: List[str] = []
            with file_path.open("rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    pages.append(page.extract_text() or "")
            return self.clean_text("\n".join(pages))
        if suffix in {".docx", ".doc"} and docx:
            document = docx.Document(str(file_path))
            return self.clean_text("\n".join(p.text for p in document.paragraphs))
        try:
            return self.clean_text(file_path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            return ""

    # -----------------------------
    # Keyword extraction
    # -----------------------------
    def extract_keywords(self, text: str, limit: Optional[int] = None) -> List[str]:
        limit = limit or self.config.keyword_limit
        text = self.clean_text(text)
        tokens = self.tokenize(text)
        counts = Counter(t for t in tokens if t not in STOPWORDS and len(t) > 2)
        boosted: Counter[str] = Counter()

        # Single-token scoring.
        for token, count in counts.items():
            score = float(count)
            if token in SKILL_HINTS:
                score += 4.0
            if token in ACTION_VERBS:
                score += 1.5
            boosted[token] += score

        text_lower = text.lower()

        # Known multi-word skills get direct boosts.
        for skill in SKILL_HINTS:
            if " " in skill and skill in text_lower:
                boosted[skill] += 6.0

        # Capitalized phrases, e.g. MongoDB Atlas, REST API, Human Resource Management.
        for phrase in re.findall(r"\b[A-Z][A-Za-z+#.]+(?:\s+[A-Z][A-Za-z+#.]+){0,3}\b", text):
            norm = phrase.strip().lower()
            parts = norm.split()
            if (
                len(norm) > 2
                and norm not in STOPWORDS
                and not norm.isdigit()
                and not any(part in STOPWORDS for part in parts)
            ):
                boosted[norm] += 2.0

        # N-gram phrases from JD/resume text. Keep only meaningful known phrases
        # or compact technical phrases ending in API/APIs. This prevents noisy phrases
        # like "developer know python" from becoming JD requirements.
        filtered = [t for t in tokens if t not in STOPWORDS and len(t) > 2]
        for n in (2, 3):
            for i in range(0, max(0, len(filtered) - n + 1)):
                phrase = " ".join(filtered[i : i + n])
                if phrase in SKILL_HINTS or phrase.endswith(" api") or phrase.endswith(" apis"):
                    boosted[phrase] += 2.5

        keywords: List[str] = []
        seen = set()
        for kw, _ in boosted.most_common(limit * 2):
            cleaned = kw.strip().lower()
            if not cleaned or cleaned in seen:
                continue
            # Avoid noisy phrases; keep known skills/technical phrases and compact nouns.
            parts = cleaned.split()
            if len(parts) > 4 or any(part in STOPWORDS for part in parts):
                continue
            if len(parts) > 1 and cleaned not in SKILL_HINTS and not cleaned.endswith(" api") and not cleaned.endswith(" apis"):
                continue
            seen.add(cleaned)
            keywords.append(cleaned)
            if len(keywords) >= limit:
                break
        return keywords

    # -----------------------------
    # Embeddings and similarity
    # -----------------------------
    def _hash_bucket(self, token: str) -> int:
        digest = hashlib.md5(token.encode("utf-8")).hexdigest()
        return int(digest[:8], 16) % self.config.embedding_dimensions

    def _lightweight_embedding(self, text: str) -> Dict[str, float]:
        tokens = [t for t in self.tokenize(text) if t not in STOPWORDS and len(t) > 2]
        features: Counter[str] = Counter(tokens)

        # Add bigrams and trigrams for semantic-ish matching without a large model.
        for n, boost in ((2, 1.35), (3, 1.15)):
            for i in range(0, max(0, len(tokens) - n + 1)):
                phrase = " ".join(tokens[i : i + n])
                if phrase in SKILL_HINTS or any(part in SKILL_HINTS for part in phrase.split()):
                    features[phrase] += boost

        vector: Dict[str, float] = defaultdict(float)
        for token, count in features.items():
            weight = 1.0 + math.log1p(float(count))
            if token in SKILL_HINTS:
                weight *= 2.2
            elif any(part in SKILL_HINTS for part in token.split()):
                weight *= 1.45
            vector[token] += weight
        return dict(vector)

    def embed_text(self, text: str) -> Any:
        if self._st_model is not None:
            return self._st_model.encode([text or ""], normalize_embeddings=True)[0]
        return self._lightweight_embedding(text)

    def cosine_similarity(self, vec_a: Any, vec_b: Any) -> float:
        if vec_a is None or vec_b is None:
            return 0.0
        if isinstance(vec_a, dict) and isinstance(vec_b, dict):
            if not vec_a or not vec_b:
                return 0.0
            common = set(vec_a) & set(vec_b)
            dot = sum(vec_a[k] * vec_b[k] for k in common)
            mag_a = math.sqrt(sum(v * v for v in vec_a.values()))
            mag_b = math.sqrt(sum(v * v for v in vec_b.values()))
            return dot / (mag_a * mag_b) if mag_a and mag_b else 0.0

        # numpy-like arrays from sentence-transformers.
        try:
            dot = float(sum(float(a) * float(b) for a, b in zip(vec_a, vec_b)))
            mag_a = math.sqrt(sum(float(a) * float(a) for a in vec_a))
            mag_b = math.sqrt(sum(float(b) * float(b) for b in vec_b))
            return dot / (mag_a * mag_b) if mag_a and mag_b else 0.0
        except Exception:
            return 0.0

    # -----------------------------
    # Explainability helpers
    # -----------------------------
    def keyword_match(self, jd_keywords: Sequence[str], resume_text: str) -> Tuple[List[str], List[str], float]:
        resume_lower = (resume_text or "").lower()
        matched: List[str] = []
        missing: List[str] = []
        seen = set()
        for kw in jd_keywords or []:
            target = str(kw).lower().strip()
            if not target or target in seen:
                continue
            seen.add(target)
            # Word boundary for short terms, substring for multi-word/technical terms.
            variants = {target}
            if target.endswith("s") and len(target) > 3:
                variants.add(target[:-1])
            else:
                variants.add(target + "s")
            ok = False
            for variant in variants:
                if " " in variant or any(ch in variant for ch in "+#."):
                    ok = ok or (variant in resume_lower)
                else:
                    ok = ok or bool(re.search(rf"\b{re.escape(variant)}\b", resume_lower))
            if ok:
                matched.append(target)
            else:
                missing.append(target)
        total = max(len(matched) + len(missing), 1)
        return matched, missing, round((len(matched) / total) * 100, 2)

    def keyword_counts(self, text: str, keywords: Sequence[str]) -> Dict[str, int]:
        text_lower = (text or "").lower()
        counts: Dict[str, int] = {}
        for kw in keywords:
            term = str(kw).lower().strip()
            if not term:
                continue
            if " " in term or any(ch in term for ch in "+#."):
                counts[term] = text_lower.count(term)
            else:
                counts[term] = len(re.findall(rf"\b{re.escape(term)}\b", text_lower))
        return counts

    def highlighted_snippets(self, text: str, keywords: Sequence[str], window: int = 80, max_snippets: int = 8) -> List[Dict[str, str]]:
        raw = text or ""
        lowered = raw.lower()
        snippets: List[Dict[str, str]] = []
        used_ranges: List[Tuple[int, int]] = []
        for kw in keywords:
            term = str(kw).strip().lower()
            if not term:
                continue
            match = re.search(re.escape(term), lowered)
            if not match:
                continue
            start, end = match.span()
            if any(abs(start - s) < 30 for s, _ in used_ranges):
                continue
            used_ranges.append((start, end))
            left = max(0, start - window)
            right = min(len(raw), end + window)
            snippet = html.escape(raw[left:right].strip())
            highlighted = re.sub(
                re.escape(html.escape(raw[start:end])),
                lambda m: f"<mark>{m.group(0)}</mark>",
                snippet,
                flags=re.IGNORECASE,
            )
            snippets.append({"keyword": term, "snippet_html": highlighted})
            if len(snippets) >= max_snippets:
                break
        return snippets

    # -----------------------------
    # Writing, grammar, structure
    # -----------------------------
    def writing_quality_score(self, text: str) -> float:
        cleaned = self.clean_text(text)
        if not cleaned:
            return 0.0
        sentences = self.sentence_split(cleaned)
        words = self.tokenize(cleaned)
        if not words:
            return 0.0

        avg_sentence = len(words) / max(len(sentences), 1)
        unique_ratio = len(set(words)) / max(len(words), 1)
        long_sentences = sum(1 for s in sentences if len(self.tokenize(s)) > 34)
        very_short = sum(1 for s in sentences if len(self.tokenize(s)) < 4)
        red_flags = sum(1 for phrase in COMMON_GRAMMAR_RED_FLAGS if phrase in cleaned.lower())
        repeated_penalty = max(0.0, 0.48 - unique_ratio) * 40
        typo_like = sum(1 for w in words if len(w) > 18 or re.search(r"(.)\1\1\1", w))

        score = 88.0
        if avg_sentence > 28:
            score -= min((avg_sentence - 28) * 0.8, 10)
        if avg_sentence < 7:
            score -= min((7 - avg_sentence) * 1.1, 8)
        score -= min(long_sentences * 3.5, 14)
        score -= min(very_short * 1.5, 8)
        score -= min(red_flags * 5, 15)
        score -= min(repeated_penalty, 12)
        score -= min(typo_like * 1.5, 8)
        if len(words) >= 180:
            score += 4
        if any(v in cleaned.lower() for v in ACTION_VERBS):
            score += 3
        return round(max(35.0, min(98.0, score)), 2)

    def structure_score(self, text: str) -> float:
        lowered = (text or "").lower()
        found_sections = sum(1 for h in SECTION_HEADERS if re.search(rf"\b{re.escape(h)}\b", lowered))
        has_email = bool(re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or ""))
        has_phone = bool(re.search(r"(?:\+?\d[\d\s\-()]{7,}\d)", text or ""))
        has_dates = bool(re.search(r"\b(?:20\d{2}|19\d{2}|present|current)\b", lowered))
        has_bullets = bool(re.search(r"(?:^|\n)\s*[-•*]", text or ""))
        word_count = len(self.tokenize(text))

        score = 55.0
        score += min(found_sections * 6, 24)
        score += 6 if has_email else 0
        score += 5 if has_phone else 0
        score += 5 if has_dates else 0
        score += 4 if has_bullets else 0
        if 180 <= word_count <= 1200:
            score += 8
        elif word_count < 80:
            score -= 15
        return round(max(20.0, min(100.0, score)), 2)

    # -----------------------------
    # Screening and ranking
    # -----------------------------
    def screen_resume(
        self,
        jd_text: str,
        resume_text: str,
        jd_keywords: Optional[Sequence[str]] = None,
        min_score: Optional[float] = None,
        candidate_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        jd_text = self.clean_text(jd_text)
        resume_text = self.clean_text(resume_text)
        minimum = float(min_score if min_score is not None else self.config.minimum_score)
        keywords = list(jd_keywords) if jd_keywords else self.extract_keywords(jd_text)

        semantic_raw = self.cosine_similarity(self.embed_text(jd_text), self.embed_text(resume_text))
        matched, missing, keyword_score = self.keyword_match(keywords, resume_text)
        # Calibrate lightweight semantic score with concept coverage. This keeps the
        # offline model practical for resumes where exact wording differs but the
        # same required skills are present.
        semantic_score = round(max(semantic_raw * 100, keyword_score * 0.92), 2)
        writing_score = self.writing_quality_score(resume_text)
        structure_score = self.structure_score(resume_text)

        weights = self.config.normalized_weights()
        final = round(
            semantic_score * weights["semantic"]
            + keyword_score * weights["keyword"]
            + writing_score * weights["writing"]
            + structure_score * weights["structure"],
            2,
        )
        recommendation = "Shortlist" if final >= minimum else "Reject"
        confidence = self._confidence_label(final, minimum)

        counts = self.keyword_counts(resume_text, matched)
        matched_details = [
            {"keyword": kw, "count": counts.get(kw, 0)} for kw in matched
        ]
        snippets = self.highlighted_snippets(resume_text, matched)

        return {
            "candidate_name": candidate_name,
            "semantic_score": semantic_score,
            "keyword_score": keyword_score,
            "writing_score": writing_score,
            "structure_score": structure_score,
            "final_score": final,
            "minimum_score": minimum,
            "recommendation": recommendation,
            "confidence": confidence,
            "matched_keywords": matched,
            "missing_keywords": missing,
            "matched_keyword_details": matched_details,
            "highlighted_snippets": snippets,
            "score_breakdown": {
                "semantic_weight": weights["semantic"],
                "keyword_weight": weights["keyword"],
                "writing_weight": weights["writing"],
                "structure_weight": weights["structure"],
            },
            "summary": self.build_report_summary(final, minimum, matched, missing, writing_score, structure_score),
        }

    def rank_applicants(
        self,
        jd_text: str,
        applicants: Sequence[ApplicantInput | Dict[str, Any]],
        jd_keywords: Optional[Sequence[str]] = None,
        min_score: Optional[float] = None,
        shortlisted_only: bool = True,
    ) -> Dict[str, Any]:
        keywords = list(jd_keywords) if jd_keywords else self.extract_keywords(jd_text)
        rows: List[Dict[str, Any]] = []
        for item in applicants:
            if isinstance(item, ApplicantInput):
                name = item.candidate_name
                resume_text = item.resume_text or (self.extract_resume_text(item.resume_path) if item.resume_path else "")
                email = item.candidate_email
                metadata = item.metadata
            else:
                name = item.get("candidate_name") or item.get("name") or "Unknown Candidate"
                resume_text = item.get("resume_text") or ""
                if not resume_text and item.get("resume_path"):
                    resume_text = self.extract_resume_text(item["resume_path"])
                email = item.get("candidate_email") or item.get("email")
                metadata = item.get("metadata") or {}

            report = self.screen_resume(jd_text, resume_text, keywords, min_score, name)
            report["candidate_email"] = email
            report["metadata"] = metadata
            rows.append(report)

        rows.sort(key=lambda r: r.get("final_score", 0), reverse=True)
        shortlisted = [r for r in rows if r.get("recommendation") == "Shortlist"]
        visible = shortlisted if shortlisted_only else rows
        return {
            "minimum_score": float(min_score if min_score is not None else self.config.minimum_score),
            "jd_keywords": keywords,
            "total_applicants": len(rows),
            "shortlisted_count": len(shortlisted),
            "rejected_count": len(rows) - len(shortlisted),
            "visible_candidates": [
                {
                    "candidate_name": r.get("candidate_name"),
                    "candidate_email": r.get("candidate_email"),
                    "final_score": r.get("final_score"),
                    "recommendation": r.get("recommendation"),
                    "matched_keywords": r.get("matched_keywords", []),
                }
                for r in visible
            ],
            "full_reports": rows,
        }

    def evaluate_answer(
        self,
        question: str,
        expected_answer: str,
        candidate_answer: str,
        keywords: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        keywords = list(keywords) if keywords else self.extract_keywords(expected_answer, limit=14)
        semantic = round(self.cosine_similarity(self.embed_text(expected_answer), self.embed_text(candidate_answer)) * 100, 2)
        matched, missing, keyword_score = self.keyword_match(keywords, candidate_answer)
        clarity = self.writing_quality_score(candidate_answer)
        final = round((semantic * 0.45) + (keyword_score * 0.30) + (clarity * 0.25), 2)
        return {
            "question": question,
            "semantic_similarity": semantic,
            "keyword_score": keyword_score,
            "clarity_score": clarity,
            "answer_score": final,
            "matched_keywords": matched,
            "missing_keywords": missing,
            "highlighted_snippets": self.highlighted_snippets(candidate_answer, matched, max_snippets=5),
            "feedback": self._answer_feedback(final, matched, missing),
        }

    def build_report_summary(
        self,
        final: float,
        minimum: float,
        matched: Sequence[str],
        missing: Sequence[str],
        writing: float,
        structure: float,
    ) -> str:
        if final >= max(85, minimum + 10):
            decision = "The applicant shows a strong match for the job description and should be prioritized."
        elif final >= minimum:
            decision = "The applicant meets the minimum criteria and can move to the next screening stage."
        else:
            decision = "The applicant does not currently meet the minimum shortlist threshold."
        matched_text = ", ".join(matched[:10]) if matched else "none"
        missing_text = ", ".join(missing[:8]) if missing else "none"
        return (
            f"{decision} Matched keywords: {matched_text}. Missing focus areas: {missing_text}. "
            f"Writing quality score: {writing}%. Resume structure score: {structure}%."
        )

    def _confidence_label(self, final: float, minimum: float) -> str:
        if final >= minimum + 15:
            return "High"
        if final >= minimum:
            return "Medium"
        if final >= minimum - 10:
            return "Low"
        return "Very Low"

    def _answer_feedback(self, final: float, matched: Sequence[str], missing: Sequence[str]) -> str:
        if final >= 80:
            base = "Strong answer with good conceptual alignment."
        elif final >= 65:
            base = "Acceptable answer, but it needs more specific detail."
        else:
            base = "Weak answer compared to the expected rubric."
        if missing:
            base += f" Missing concepts: {', '.join(list(missing)[:5])}."
        if matched:
            base += f" Covered: {', '.join(list(matched)[:5])}."
        return base


_default_model = RecruitmentScreeningModel()


def get_default_screening_model() -> RecruitmentScreeningModel:
    return _default_model
