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
import subprocess
import tempfile
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import PyPDF2
except Exception:  # optional dependency
    PyPDF2 = None

try:
    import pdfplumber
except Exception:  # optional dependency
    pdfplumber = None

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
    "mongodb", "mongo", "nosql", "document database", "document db", "postgresql", "mysql", "sql", "redis", "celery", "rabbitmq",
    "docker", "kubernetes", "aws", "azure", "gcp", "linux", "nginx", "gunicorn", "git",
    "github", "gitlab", "rest", "api", "apis", "graphql", "microservices", "oauth", "jwt",
    "machine learning", "deep learning", "nlp", "ai", "rag", "llm", "transformers", "rest api", "rest apis",
    "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "opencv", "analytics",
    "hrms", "payroll", "attendance", "recruitment", "onboarding", "performance", "compliance",
    "communication", "leadership", "management", "stakeholder", "negotiation", "sourcing",
    "screening", "interviewing", "employee relations", "talent acquisition",
}


SKILL_ALIASES = {
    "mongodb": ["mongo db", "mongo", "mongodb atlas", "document database", "document db", "nosql", "no sql", "non relational database", "non-relational database"],
    "nosql": ["mongodb", "mongo db", "mongo", "document database", "document db", "non relational database", "non-relational database"],
    "rest api": ["rest", "restful api", "rest apis", "api", "apis", "web api", "http api"],
    "flask": ["flask framework", "python flask", "flask backend"],
    "javascript": ["js", "ecmascript"],
    "machine learning": ["ml", "predictive modeling", "predictive analytics", "model training"],
    "deep learning": ["neural network", "neural networks", "cnn", "lstm", "transformer"],
    "nlp": ["natural language processing", "text processing", "language processing"],
    "transformers": ["hugging face", "huggingface", "llm", "large language model", "language model"],
    "opencv": ["computer vision", "cv", "image processing"],
    "yolo": ["yolov8", "object detection", "defect detection"],
    "dash": ["plotly dash", "plotly", "analytics dashboard", "dashboard"],
    "git": ["github", "version control", "repo management", "repository management"],
    "aws": ["amazon web services", "cloud deployment"],
    "azure": ["microsoft azure", "cloud"],
    "scrum": ["agile", "sprints", "sprint", "kanban"],
    "hrms": ["human resource management system", "hr management system", "peopleops"],
}

SKILL_CATEGORIES = {
    "backend": {"python", "flask", "django", "fastapi", "rest api", "api", "sqlalchemy", "jinja2"},
    "database": {"mongodb", "nosql", "mysql", "postgresql", "sql", "redis"},
    "frontend": {"javascript", "html", "css", "tailwind", "bootstrap", "react"},
    "ai_ml": {"machine learning", "deep learning", "nlp", "transformers", "tensorflow", "keras", "scikit-learn", "pandas", "numpy", "lstm", "llm"},
    "computer_vision": {"opencv", "yolo", "computer vision", "ocr", "defect detection"},
    "devops": {"git", "github", "docker", "aws", "azure", "linux", "nginx", "gunicorn"},
    "analytics": {"dash", "plotly", "tableau", "power bi", "matplotlib", "business intelligence"},
    "process": {"agile", "scrum", "kanban", "documentation", "testing", "code review"},
}

DEGREE_TERMS = {"bachelor", "bachelors", "master", "masters", "bca", "mca", "computer applications", "computer science", "information technology", "engineering"}
CERT_TERMS = {"certification", "certified", "certificate", "aws certified", "azure certification"}

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

    def _alias_pattern(self, term: str) -> str:
        """Build a tolerant regex for technical terms.

        This treats spaces, hyphens, underscores and slashes as equivalent, so
        values such as ``MongoDB/NoSQL``, ``mongo db``, ``MongoDB Atlas`` and
        ``non-relational database`` can be matched reliably.
        """
        escaped = re.escape(str(term or "").strip())
        escaped = escaped.replace(r"\ ", r"[\s\-_/]+")
        escaped = escaped.replace(r"\-", r"[\s\-_/]+")
        escaped = escaped.replace(r"_", r"[\s\-_/]+")
        escaped = escaped.replace(r"/", r"[\s\-_/]+")
        return escaped

    def _split_keyword_terms(self, value: str) -> List[str]:
        """Split recruiter-entered composite keywords into screenable terms.

        Recruiters commonly type skills as ``MongoDB/NoSQL`` or
        ``Flask, Django / FastAPI``. Earlier versions treated the whole string as
        one exact keyword, which caused false misses. This function expands the
        composite value while preserving meaningful multi-word skills.
        """
        value = str(value or "").strip().lower()
        if not value:
            return []

        normalized = re.sub(r"[|;]+", ",", value)
        pieces = []
        for chunk in re.split(r",|\n", normalized):
            chunk = chunk.strip(" -•*\t")
            if not chunk:
                continue
            # Split slash-separated skill packs, but keep URL-like text out of JD keywords.
            if "/" in chunk and not re.search(r"https?://", chunk):
                pieces.extend(part.strip() for part in re.split(r"/+", chunk) if part.strip())
            else:
                pieces.append(chunk)
        return [p for p in pieces if p]

    def canonical_skill(self, term: str) -> str:
        """Return the canonical skill family for a term when known."""
        target = str(term or "").lower().strip()
        target = re.sub(r"\s+", " ", target)
        for canonical, aliases in SKILL_ALIASES.items():
            all_terms = {canonical, *aliases}
            for item in all_terms:
                pattern = r"^" + self._alias_pattern(item) + r"$"
                if re.match(pattern, target, flags=re.IGNORECASE):
                    return canonical
        return target

    def expand_keywords(self, keywords: Sequence[str] | str | None) -> List[str]:
        """Normalize recruiter/JD keywords into canonical, alias-aware entries."""
        if not keywords:
            return []
        if isinstance(keywords, str):
            raw_items = self._split_keyword_terms(keywords)
        else:
            raw_items = []
            for item in keywords:
                raw_items.extend(self._split_keyword_terms(str(item)))

        expanded: List[str] = []
        seen = set()
        for item in raw_items:
            canonical = self.canonical_skill(item)
            for candidate in (canonical, item):
                candidate = str(candidate or "").lower().strip()
                if candidate and candidate not in seen:
                    seen.add(candidate)
                    expanded.append(candidate)
        return expanded

    def canonicalize_text(self, text: str) -> str:
        """Normalize technical aliases so semantic/keyword checks handle variants.

        Example: MongoDB, Mongo DB, NoSQL, document database, and MongoDB Atlas
        all reinforce the same family instead of being treated as unrelated words.
        Replacements are done with placeholders first so broad aliases like
        ``api`` do not repeatedly rewrite text that has already been normalized.
        """
        original = text or ""
        normalized = original
        placeholders: Dict[str, str] = {}
        index = 0

        all_aliases: List[Tuple[str, str]] = []
        for canonical, aliases in SKILL_ALIASES.items():
            for term in set([canonical, *aliases]):
                all_aliases.append((term, canonical))
        all_aliases.sort(key=lambda item: len(item[0]), reverse=True)

        for term, canonical in all_aliases:
            pattern = r"(?<![A-Za-z0-9])" + self._alias_pattern(term) + r"(?![A-Za-z0-9])"

            def repl(_match, canonical=canonical):
                nonlocal index
                key = f" __SKILL_ALIAS_{index}__ "
                placeholders[key.strip()] = canonical
                index += 1
                return key

            normalized = re.sub(pattern, repl, normalized, flags=re.IGNORECASE)

        for placeholder, canonical in placeholders.items():
            normalized = normalized.replace(placeholder, canonical)
        return normalized

    def tokenize(self, text: str) -> List[str]:
        # Add spaces around slashes before canonicalization so MongoDB/NoSQL is
        # considered as two related skills rather than one unknown token.
        text = re.sub(r"(?<=[A-Za-z0-9])/(?=[A-Za-z0-9])", " / ", text or "")
        text = self.canonicalize_text(text)
        raw = re.findall(r"[A-Za-z][A-Za-z0-9+#.\-]{1,}", text or "")
        return [t.lower().strip(".-") for t in raw if t.strip(".-")]

    def sentence_split(self, text: str) -> List[str]:
        chunks = re.split(r"(?<=[.!?])\s+|\n+", text or "")
        return [c.strip() for c in chunks if c and c.strip()]

    def _extract_pdf_text(self, file_path: Path) -> str:
        """Extract text from a PDF using multiple safe fallbacks."""
        pages: List[str] = []

        # Primary lightweight path: PyPDF2.
        if PyPDF2 is not None:
            try:
                with file_path.open("rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        pages.append(page.extract_text() or "")
                text = self.clean_text("\n".join(pages))
                if len(text) > 25:
                    return text
            except Exception:
                pages = []

        # Fallback: pdfplumber, better for many resume PDFs with columns/tables.
        if pdfplumber is not None:
            try:
                with pdfplumber.open(str(file_path)) as pdf:
                    pages = [page.extract_text(x_tolerance=1, y_tolerance=3) or "" for page in pdf.pages]
                text = self.clean_text("\n".join(pages))
                if len(text) > 25:
                    return text
            except Exception:
                pass

        # Last fallback for odd PDFs: read raw bytes and recover visible strings.
        try:
            raw = file_path.read_bytes().decode("latin-1", errors="ignore")
            raw = re.sub(r"[^A-Za-z0-9@+.#:/,_\-\s]", " ", raw)
            return self.clean_text(raw)
        except Exception:
            return ""

    def _extract_docx_text(self, file_path: Path) -> str:
        """Extract text from DOCX including paragraphs, tables, headers/footers."""
        if docx is None:
            return ""
        try:
            document = docx.Document(str(file_path))
            parts: List[str] = []

            for paragraph in document.paragraphs:
                if paragraph.text:
                    parts.append(paragraph.text)

            for table in document.tables:
                for row in table.rows:
                    for cell in row.cells:
                        if cell.text:
                            parts.append(cell.text)

            for section in document.sections:
                for paragraph in section.header.paragraphs:
                    if paragraph.text:
                        parts.append(paragraph.text)
                for paragraph in section.footer.paragraphs:
                    if paragraph.text:
                        parts.append(paragraph.text)

            return self.clean_text("\n".join(parts))
        except Exception:
            return ""

    def _extract_legacy_doc_text(self, file_path: Path) -> str:
        """Best-effort extraction for legacy .doc files.

        Python-docx cannot read old binary .doc files. This function first tries
        common local converters when available, then falls back to recovering
        readable strings from the binary file so the screening process still has
        usable text instead of silently failing.
        """
        for command in (["antiword", str(file_path)], ["catdoc", str(file_path)]):
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=10)
                text = self.clean_text(result.stdout or "")
                if len(text) > 25:
                    return text
            except Exception:
                continue

        # Some files are mislabeled as .doc but are actually DOCX archives.
        if zipfile.is_zipfile(file_path):
            text = self._extract_docx_text(file_path)
            if text:
                return text

        try:
            data = file_path.read_bytes()
            strings = re.findall(rb"[A-Za-z0-9@+.#:/,_\- ]{4,}", data)
            decoded = "\n".join(x.decode("latin-1", errors="ignore") for x in strings)
            return self.clean_text(decoded)
        except Exception:
            return ""

    def extract_resume_text(self, path: str | Path) -> str:
        """Extract readable text from a resume file.

        This method is intentionally format-aware, but it does not decide where
        the extracted text is stored. Routes should call
        ``convert_resume_to_txt`` first so every PDF/DOC/DOCX/RTF/TEX upload has
        a saved normalized .txt copy, then screen using that .txt content.
        """
        file_path = Path(path)
        suffix = file_path.suffix.lower()

        if not file_path.exists():
            return ""

        if suffix == ".pdf":
            return self._extract_pdf_text(file_path)

        if suffix == ".docx":
            return self._extract_docx_text(file_path)

        if suffix == ".doc":
            return self._extract_legacy_doc_text(file_path)

        if suffix in {".txt", ".tex", ".md", ".rtf"}:
            try:
                return self.clean_text(file_path.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                try:
                    return self.clean_text(file_path.read_text(encoding="latin-1", errors="ignore"))
                except Exception:
                    return ""

        # Final fallback for allowed unknown text-like files.
        try:
            return self.clean_text(file_path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            return ""

    def convert_resume_to_txt(self, source_path: str | Path, txt_path: str | Path | None = None) -> Dict[str, Any]:
        """Convert any supported resume format into a normalized .txt file.

        Screening should always run against this normalized text file. That gives
        the recruitment module a single predictable input format and makes failed
        parsing easy to inspect during testing.
        """
        source = Path(source_path)
        if txt_path is None:
            txt_dir = source.parent / "converted_txt"
            txt_dir.mkdir(parents=True, exist_ok=True)
            txt_path = txt_dir / f"{source.stem}.txt"
        else:
            txt_path = Path(txt_path)
            txt_path.parent.mkdir(parents=True, exist_ok=True)

        text = self.extract_resume_text(source)
        text = self.clean_text(text)
        ok = len(text.strip()) >= 25

        if ok:
            Path(txt_path).write_text(text, encoding="utf-8")

        return {
            "ok": ok,
            "source_path": str(source),
            "txt_path": str(txt_path) if ok else None,
            "text": text,
            "char_count": len(text),
            "word_count": len(self.tokenize(text)),
            "source_extension": source.suffix.lower(),
            "message": "Resume converted to normalized text" if ok else "Could not extract enough readable text for screening",
        }

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
        canonical_lower = self.canonicalize_text(text).lower()

        # Known skills and aliases get direct boosts. This is important for terms
        # such as MongoDB/NoSQL where the recruiter and resume may use different
        # but equivalent phrasing.
        for skill in SKILL_HINTS:
            if self._term_in_text(skill, canonical_lower + " " + text_lower):
                boosted[self.canonical_skill(skill)] += 6.0 if " " in skill else 4.0

        for canonical, aliases in SKILL_ALIASES.items():
            if any(self._term_in_text(term, canonical_lower + " " + text_lower) for term in [canonical, *aliases]):
                boosted[canonical] += 7.0

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
                if phrase in SKILL_HINTS or (n == 2 and (phrase.endswith(" api") or phrase.endswith(" apis"))):
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
            if len(parts) > 1 and cleaned not in SKILL_HINTS and not (len(parts) == 2 and (cleaned.endswith(" api") or cleaned.endswith(" apis"))):
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
    def keyword_variants(self, keyword: str) -> List[str]:
        targets = self.expand_keywords([keyword]) or [str(keyword or "").lower().strip()]
        variants = set()
        for target in targets:
            target = str(target or "").lower().strip()
            if not target:
                continue
            variants.add(target)
            canonical = self.canonical_skill(target)
            variants.add(canonical)
            if canonical in SKILL_ALIASES:
                variants.update(SKILL_ALIASES[canonical])
            for known_canonical, aliases in SKILL_ALIASES.items():
                if target == known_canonical or target in aliases or canonical == known_canonical:
                    variants.add(known_canonical)
                    variants.update(aliases)

        expanded = set()
        for item in variants:
            item = str(item or "").strip()
            if not item:
                continue
            if item.endswith("s") and len(item) > 3:
                expanded.add(item[:-1])
            else:
                expanded.add(item + "s")
            expanded.add(item)
        return sorted(expanded, key=len, reverse=True)

    def _term_in_text(self, term: str, text_lower: str) -> bool:
        if not term:
            return False
        pattern = self._alias_pattern(term)
        return bool(re.search(rf"(?<![A-Za-z0-9]){pattern}(?![A-Za-z0-9])", text_lower, flags=re.IGNORECASE))

    def keyword_match(self, jd_keywords: Sequence[str], resume_text: str) -> Tuple[List[str], List[str], float]:
        resume_lower = self.canonicalize_text(resume_text or "").lower() + " " + (resume_text or "").lower()
        matched: List[str] = []
        missing: List[str] = []
        seen = set()
        normalized_keywords = self.expand_keywords(jd_keywords)
        for kw in normalized_keywords or []:
            target = self.canonical_skill(str(kw).lower().strip())
            if not target or target in seen:
                continue
            seen.add(target)
            ok = any(self._term_in_text(variant, resume_lower) for variant in self.keyword_variants(target))
            if ok:
                matched.append(target)
            else:
                missing.append(target)
        total = max(len(matched) + len(missing), 1)
        return matched, missing, round((len(matched) / total) * 100, 2)

    def keyword_counts(self, text: str, keywords: Sequence[str]) -> Dict[str, int]:
        text_lower = self.canonicalize_text(text or "").lower() + " " + (text or "").lower()
        counts: Dict[str, int] = {}
        for kw in keywords:
            term = str(kw).lower().strip()
            if not term:
                continue
            total = 0
            for variant in self.keyword_variants(term):
                pattern = re.escape(variant).replace(r"\ ", r"[\s\-_/]+")
                if " " in variant or any(ch in variant for ch in "+#."):
                    total += len(re.findall(pattern, text_lower, flags=re.IGNORECASE))
                else:
                    total += len(re.findall(rf"\b{pattern}\b", text_lower, flags=re.IGNORECASE))
            counts[term] = total
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
            match = None
            for variant in self.keyword_variants(term):
                pattern = self._alias_pattern(variant)
                match = re.search(pattern, lowered, flags=re.IGNORECASE)
                if match:
                    break
            if not match:
                continue
            start, end = match.span()
            if any(abs(start - s) < 30 for s, _ in used_ranges):
                continue
            used_ranges.append((start, end))
            left = max(0, start - window)
            right = min(len(raw), end + window)
            snippet_raw = raw[left:right].strip()
            # Highlight the exact matched surface text, even if it was an alias
            # such as NoSQL for the canonical MongoDB keyword.
            rel_start = max(0, start - left)
            rel_end = max(rel_start, end - left)
            highlighted_raw = (
                snippet_raw[:rel_start]
                + "[[MARK]]"
                + snippet_raw[rel_start:rel_end]
                + "[[/MARK]]"
                + snippet_raw[rel_end:]
            )
            highlighted = html.escape(highlighted_raw).replace("[[MARK]]", "<mark>").replace("[[/MARK]]", "</mark>")
            snippets.append({"keyword": term, "snippet_html": highlighted})
            if len(snippets) >= max_snippets:
                break
        return snippets

    def section_presence(self, text: str) -> Dict[str, bool]:
        lower = (text or "").lower()
        return {
            "contact": bool(re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or "")) or bool(re.search(r"\+?\d[\d\s-]{8,}", text or "")),
            "skills": any(h in lower for h in ["skills", "technical skills", "technologies"]),
            "experience": any(h in lower for h in ["experience", "work experience", "intern", "employment"]),
            "projects": "project" in lower or "projects" in lower,
            "education": "education" in lower or any(t in lower for t in DEGREE_TERMS),
            "certifications": any(t in lower for t in CERT_TERMS),
        }

    def ats_compatibility_checks(self, text: str) -> Dict[str, Any]:
        lower = (text or "").lower()
        sections = self.section_presence(text)
        words = self.tokenize(text)
        action_count = sum(1 for v in ACTION_VERBS if re.search(rf"\b{re.escape(v)}\b", lower))
        quantified = len(re.findall(r"\b\d+(?:\.\d+)?%?\b", text or ""))
        issues = []
        if not sections["contact"]:
            issues.append("Contact details were not clearly detected.")
        if not sections["skills"]:
            issues.append("Skills section is missing or non-standard.")
        if not sections["experience"]:
            issues.append("Experience/internship section is missing or hard to parse.")
        if len(words) < 120:
            issues.append("Resume text is very short for reliable screening.")
        if action_count < 3:
            issues.append("Few achievement/action verbs were detected.")
        if quantified < 2:
            issues.append("Few quantified achievements or metrics were detected.")
        score = 55
        score += sum(6 for present in sections.values() if present)
        score += min(action_count * 2, 12)
        score += min(quantified * 3, 12)
        score = max(0, min(100, score))
        return {"score": round(score, 2), "sections": sections, "issues": issues, "action_verb_count": action_count, "metric_count": quantified}

    def category_fit_scores(self, jd_text: str, resume_text: str, jd_keywords: Sequence[str]) -> Dict[str, float]:
        jd_all = set(self.extract_keywords(jd_text, limit=80)) | {str(k).lower() for k in jd_keywords or []}
        resume_lower = self.canonicalize_text(resume_text or "").lower() + " " + (resume_text or "").lower()
        scores = {}
        for category, terms in SKILL_CATEGORIES.items():
            expected = sorted(t for t in terms if t in jd_all or any(self._term_in_text(t, self.canonicalize_text(jd_text).lower()) for _ in [0]))
            if not expected:
                # If JD does not emphasize this category, leave it neutral rather than penalizing.
                continue
            matched = sum(1 for term in expected if any(self._term_in_text(v, resume_lower) for v in self.keyword_variants(term)))
            scores[category] = round((matched / max(len(expected), 1)) * 100, 2)
        return scores

    def extract_experience_years(self, text: str) -> Optional[float]:
        lower = (text or "").lower()
        found = []
        for m in re.findall(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", lower):
            try:
                found.append(float(m))
            except Exception:
                pass
        return max(found) if found else None

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

        # Blend manual JD keywords + extracted JD keywords so a recruiter can type
        # MongoDB/NoSQL and still match Mongo DB, document DB, or MongoDB Atlas in
        # a resume. Canonical aliases are included for explainable matching.
        base_keywords = self.expand_keywords(jd_keywords)
        extracted_keywords = self.extract_keywords(jd_text)
        keywords = []
        seen = set()
        for kw in [*base_keywords, *self.expand_keywords(extracted_keywords)]:
            target = self.canonical_skill(str(kw).lower().strip())
            if not target or target in seen:
                continue
            seen.add(target)
            keywords.append(target)

        canonical_jd = self.canonicalize_text(jd_text)
        canonical_resume = self.canonicalize_text(resume_text)
        semantic_raw = self.cosine_similarity(self.embed_text(canonical_jd), self.embed_text(canonical_resume))
        matched, missing, keyword_score = self.keyword_match(keywords, resume_text)

        # ATS-style screeners usually combine semantic fit with keyword coverage and
        # parse quality. Keep synonym coverage influential so phrasing differences do
        # not unfairly reject a good candidate.
        semantic_score = round(max(semantic_raw * 100, keyword_score * 0.92), 2)
        writing_score = self.writing_quality_score(resume_text)
        structure_score = self.structure_score(resume_text)
        ats_checks = self.ats_compatibility_checks(resume_text)
        category_scores = self.category_fit_scores(jd_text, resume_text, keywords)
        experience_years = self.extract_experience_years(resume_text)

        weights = self.config.normalized_weights()
        final = round(
            semantic_score * weights["semantic"]
            + keyword_score * weights["keyword"]
            + writing_score * weights["writing"]
            + structure_score * weights["structure"],
            2,
        )

        # Small parse-quality adjustment: reward resumes that parse cleanly and use
        # standard ATS sections, penalize very weak parse quality.
        if ats_checks["score"] >= 88:
            final = min(100.0, round(final + 2.0, 2))
        elif ats_checks["score"] < 62:
            final = max(0.0, round(final - 4.0, 2))

        recommendation = "Shortlist" if final >= minimum else "Reject"
        confidence = self._confidence_label(final, minimum)

        counts = self.keyword_counts(resume_text, matched)
        matched_details = [
            {"keyword": kw, "count": counts.get(kw, 0), "aliases_checked": self.keyword_variants(kw)} for kw in matched
        ]
        snippets = self.highlighted_snippets(resume_text, matched)

        return {
            "candidate_name": candidate_name,
            "semantic_score": semantic_score,
            "keyword_score": keyword_score,
            "writing_score": writing_score,
            "structure_score": structure_score,
            "ats_score": ats_checks.get("score"),
            "final_score": final,
            "minimum_score": minimum,
            "recommendation": recommendation,
            "confidence": confidence,
            "matched_keywords": matched,
            "missing_keywords": missing,
            "matched_keyword_details": matched_details,
            "highlighted_snippets": snippets,
            "category_scores": category_scores,
            "ats_checks": ats_checks,
            "experience_years_detected": experience_years,
            "score_breakdown": {
                "semantic_weight": weights["semantic"],
                "keyword_weight": weights["keyword"],
                "writing_weight": weights["writing"],
                "structure_weight": weights["structure"],
                "ats_adjustment_note": "ATS parse quality can add up to +2 or subtract up to -4 after weighted scoring.",
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
        keywords = self.expand_keywords(jd_keywords) if jd_keywords else self.extract_keywords(jd_text)
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
