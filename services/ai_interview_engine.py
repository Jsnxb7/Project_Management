"""Runtime AI interview engine attached to configured interview rooms."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from bson import ObjectId

TECH_KEYWORDS = {
    "python": "Python", "flask": "Flask", "mongodb": "MongoDB", "json": "JSON", "api": "API", "rest": "REST API",
    "html": "HTML", "css": "CSS", "javascript": "JavaScript", "jinja": "Jinja2", "jinja2": "Jinja2",
    "sql": "SQL", "nosql": "NoSQL", "stt": "STT", "tts": "TTS", "gtts": "gTTS", "whisper": "Whisper",
    "transformer": "Transformers", "sentence-transformers": "sentence-transformers", "language-tool": "language-tool-python",
    "dashboard": "Dashboard", "hrms": "HRMS", "shortlisting": "Shortlisting", "interview": "Interview System",
    "debug": "Debugging", "team": "Teamwork", "communication": "Communication", "yolo": "YOLO", "opencv": "OpenCV", "lstm": "LSTM",
}

CHECKLIST = [
    ("name", "Could you please provide your full name?"),
    ("current_status", "What are you currently studying, working on, or focusing on?"),
    ("education", "Can you tell me about your educational background?"),
    ("skills", "What technical skills or tools are you most comfortable with?"),
    ("projects", "Can you explain one important project you have worked on?"),
    ("experience", "Can you describe your practical development, internship, or work experience?"),
    ("challenges", "Can you describe one challenge you faced in a project and how you solved it?"),
    ("strengths", "What would you say is one of your main strengths as a developer?"),
    ("career_goals", "What kind of role or opportunity are you looking for next?"),
    ("availability", "When would you be available for the next round or to start if selected?"),
]


def utcnow():
    return datetime.now(timezone.utc)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def extract_name(text: str) -> Optional[str]:
    for pat in [r"my full name is\s+([A-Za-z][A-Za-z .'-]{1,70})", r"my name is\s+([A-Za-z][A-Za-z .'-]{1,70})", r"name is\s+([A-Za-z][A-Za-z .'-]{1,70})"]:
        m = re.search(pat, text or "", flags=re.I)
        if m:
            val = re.split(r"[.!?,;]|\band\b|\bi am\b", m.group(1), flags=re.I)[0].strip()
            return val.title() if val else None
    return None


def keywords(text: str) -> List[str]:
    low = (text or "").lower()
    out = []
    for token, label in TECH_KEYWORDS.items():
        if token in low and label not in out:
            out.append(label)
    return out


def detect_fields(answer: str, target_field: str = None) -> Dict[str, Any]:
    answer = clean(answer)
    low = answer.lower()
    matches = []
    name = extract_name(answer)
    if name:
        matches.append({"field": "name", "score": 0.99, "source": "strict_name_rule"})
    if any(x in low for x in ["currently", "right now", "pursuing", "working on", "studying", "learning"]):
        matches.append({"field": "current_status", "score": 0.78, "source": "rule"})
    if any(x in low for x in ["bca", "mca", "degree", "university", "college", "education", "bachelor", "master"]):
        matches.append({"field": "education", "score": 0.9, "source": "rule"})
    if keywords(answer):
        matches.append({"field": "skills", "score": 0.8, "source": "keywords"})
    if any(x in low for x in ["project", "platform", "system", "application", "module", "built", "developed"]):
        matches.append({"field": "projects", "score": 0.85, "source": "rule"})
    if any(x in low for x in ["intern", "experience", "worked", "role", "responsible", "review", "sprint", "debug"]):
        matches.append({"field": "experience", "score": 0.76, "source": "rule"})
    if any(x in low for x in ["challenge", "problem", "issue", "debug", "solved", "error"]):
        matches.append({"field": "challenges", "score": 0.9, "source": "rule"})
    if any(x in low for x in ["strength", "team", "collaborat", "communication", "leadership"]):
        matches.append({"field": "strengths", "score": 0.86, "source": "rule"})
    if any(x in low for x in ["goal", "future", "looking for", "role", "opportunity", "career"]):
        matches.append({"field": "career_goals", "score": 0.72, "source": "rule"})
    if any(x in low for x in ["available", "availability", "join", "start", "next round", "schedule", "onboarding"]):
        matches.append({"field": "availability", "score": 0.92, "source": "strict_availability_rule"})
    if target_field and not any(m["field"] == target_field for m in matches) and len(answer) > 25:
        matches.append({"field": target_field, "score": 0.55, "source": "target_context"})
    matches = sorted(matches, key=lambda x: x["score"], reverse=True)
    return {"best_field": matches[0]["field"] if matches else (target_field or "unclear"), "field_score": matches[0]["score"] if matches else 0.0, "matched_fields": matches[:6], "keywords": keywords(answer)}


def score_language(text: str) -> Dict[str, Any]:
    words = re.findall(r"\b[a-zA-Z][a-zA-Z'-]*\b", text or "")
    unique = len(set(w.lower() for w in words))
    total = max(1, len(words))
    vocab = min(100, int((unique / total) * 145))
    sentence_count = max(1, len(re.findall(r"[.!?]", text or "")))
    avg_len = total / sentence_count
    fluency = 100 if 6 <= avg_len <= 35 else 85
    return {"grammar_score": 90, "vocabulary_score": vocab, "fluency_score": fluency, "overall_language_score": int(0.4 * 90 + 0.3 * vocab + 0.3 * fluency), "issues": []}


def analyse_answer(question: Dict[str, Any], answer: str, filled_before: Dict[str, bool]) -> Dict[str, Any]:
    target = question.get("target_field")
    detected = detect_fields(answer, target)
    lang = score_language(answer)
    field_updates = {}
    for m in detected["matched_fields"]:
        # Save evidence liberally, but completion is controlled separately by target/current field.
        field_updates[m["field"]] = m["score"]
    complete_field = target if target and len(clean(answer)) >= 10 else detected["best_field"]
    filled_after = dict(filled_before or {})
    if complete_field in filled_after and detected["field_score"] >= 0.5:
        filled_after[complete_field] = True
    return {
        "target_field": target,
        "best_field": detected["best_field"],
        "field_score": detected["field_score"],
        "matched_fields": detected["matched_fields"],
        "keywords": detected["keywords"],
        "field_updates": field_updates,
        "filled_fields_after_answer": filled_after,
        "language_score": lang,
        "technical_relevance_score": min(100, 55 + len(detected["keywords"]) * 5),
        "project_depth_score": 80 if "projects" in field_updates or "challenges" in field_updates else 65,
        "communication_score": lang["overall_language_score"],
        "role_fit_score": min(100, 60 + len([k for k in detected["keywords"] if k in ["Python", "Flask", "MongoDB", "JSON", "API"]]) * 7),
        "summary": clean(answer)[:260],
        "strengths": ["Provides relevant practical evidence"] if detected["keywords"] else [],
        "weaknesses": [] if len(clean(answer)) > 45 else ["Answer is brief and may need more detail"],
        "analysed_at": utcnow(),
    }


def initial_memory(candidate_name: str = None) -> Dict[str, Any]:
    return {
        "filled_fields": {field: False for field, _ in CHECKLIST},
        "candidate_profile": {"name": candidate_name, "skills": [], "projects": [], "experience": [], "challenges": [], "strengths": [], "extra_notes": []},
        "field_evidence": {field: [] for field, _ in CHECKLIST},
        "asked_forced_question_ids": [],
        "normal_index": 0,
    }


def update_memory(memory: Dict[str, Any], question: Dict[str, Any], answer: str, analysis: Dict[str, Any]):
    memory.setdefault("field_evidence", {field: [] for field, _ in CHECKLIST})
    memory.setdefault("candidate_profile", {})
    memory.setdefault("filled_fields", {field: False for field, _ in CHECKLIST})
    target = question.get("target_field") or analysis.get("best_field")
    evidence = {"answer": answer, "confidence": analysis.get("field_score"), "source": question.get("question_source") or question.get("source") or question.get("question_type"), "timestamp": utcnow()}
    if target:
        memory["field_evidence"].setdefault(target, []).append(evidence)
    for m in analysis.get("matched_fields", []):
        if m["field"] != target and m.get("score", 0) >= 0.76:
            memory["field_evidence"].setdefault(m["field"], []).append({**evidence, "confidence": m.get("score")})
    memory["filled_fields"] = analysis.get("filled_fields_after_answer", memory.get("filled_fields", {}))
    name = extract_name(answer)
    if name:
        memory["candidate_profile"]["name"] = name
    for kw in analysis.get("keywords", []):
        if kw not in memory["candidate_profile"].setdefault("skills", []):
            memory["candidate_profile"]["skills"].append(kw)
    if target in ["current_status", "education", "career_goals", "availability"]:
        memory["candidate_profile"][target] = answer
    elif target in ["projects", "experience", "challenges", "strengths"]:
        memory["candidate_profile"].setdefault(target, [])
        if answer not in memory["candidate_profile"][target]:
            memory["candidate_profile"][target].append(answer)
    if question.get("id") and question.get("question_type") == "rag_forced":
        if question["id"] not in memory.setdefault("asked_forced_question_ids", []):
            memory["asked_forced_question_ids"].append(question["id"])


def next_question(config: Dict[str, Any], memory: Dict[str, Any]) -> Dict[str, Any]:
    forced = config.get("forced_questions", [])
    asked = set(memory.get("asked_forced_question_ids", []))
    # Keep a natural blend: ask forced questions once available, otherwise fill checklist.
    for q in forced:
        if q.get("id") not in asked and not q.get("asked"):
            return {**q, "question_source": q.get("source"), "question_type": "rag_forced"}
    for field, question in CHECKLIST:
        if not memory.get("filled_fields", {}).get(field):
            return {"id": f"normal_{field}", "source": "checklist", "question_source": "checklist", "target_field": field, "question_type": "primary", "question": question}
    return {"id": "closing", "source": "system", "question_source": "system", "target_field": None, "question_type": "closing", "question": "Thank you for your answers. This completes the interview."}


def final_scores(transcript: Dict[str, Any]) -> Dict[str, Any]:
    answers = transcript.get("answers", [])
    if not answers:
        return {"overall_score": 0, "category_scores": {}}
    cats = {"technical_relevance": [], "project_explanation": [], "problem_solving": [], "communication": [], "role_fit": [], "language": []}
    for a in answers:
        an = a.get("answer_analysis", {})
        cats["technical_relevance"].append(an.get("technical_relevance_score", 60))
        cats["project_explanation"].append(an.get("project_depth_score", 60))
        cats["problem_solving"].append(80 if an.get("best_field") == "challenges" else 65)
        cats["communication"].append(an.get("communication_score", 70))
        cats["role_fit"].append(an.get("role_fit_score", 60))
        cats["language"].append((an.get("language_score") or {}).get("overall_language_score", 70))
    category_scores = {k: round(sum(v) / len(v), 2) if v else 0 for k, v in cats.items()}
    overall = round(category_scores["technical_relevance"] * 0.3 + category_scores["project_explanation"] * 0.2 + category_scores["problem_solving"] * 0.15 + category_scores["communication"] * 0.15 + category_scores["role_fit"] * 0.1 + category_scores["language"] * 0.1, 2)
    return {"overall_score": overall, "category_scores": category_scores}
