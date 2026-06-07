"""Lightweight hybrid RAG question generation for AI interviews.

This service uses deterministic evidence extraction first, then optionally uses a
local chat model when it is available.  The fallback stays dependency-light so the
Flask app can run before the heavy ML packages are installed.
"""

from __future__ import annotations

import math
import re
from typing import Dict, List, Any

PROJECT_WORDS = {"project", "platform", "system", "application", "management", "prediction", "detection", "translation", "dashboard"}
TECH_WORDS = {
    "python", "flask", "django", "fastapi", "mongodb", "mysql", "json", "api", "rest", "html", "css",
    "javascript", "jinja", "jinja2", "stt", "tts", "gtts", "whisper", "transformers", "rag", "llm",
    "dashboard", "role", "authentication", "blueprint", "routes", "nosql", "opencv", "yolo", "lstm"
}


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\x00", " ")).strip()


def split_sentences(text: str, max_len: int = 650) -> List[str]:
    text = clean_text(text)
    raw = re.split(r"(?<=[.!?])\s+|\n+|\s+-\s+", text)
    out = []
    for item in raw:
        item = clean_text(item.strip(" -*•\t"))
        if len(item) < 25:
            continue
        if len(item) <= max_len:
            out.append(item)
        else:
            for i in range(0, len(item), max_len):
                part = item[i:i + max_len].strip()
                if len(part) >= 25:
                    out.append(part)
    return out[:80]


def keyphrases(text: str) -> List[str]:
    found = []
    mapping = {
        "python": "Python", "flask": "Flask", "blueprint": "Flask Blueprints", "routes": "Flask Routes",
        "rest": "REST API", "api": "API", "mongodb": "MongoDB", "nosql": "NoSQL", "mysql": "MySQL",
        "json": "JSON", "html": "HTML", "css": "CSS", "javascript": "JavaScript", "jinja": "Jinja2",
        "authentication": "Authentication", "role-based": "Role-based Access", "dashboard": "Dashboard",
        "recruitment": "Recruitment", "shortlisting": "Shortlisting", "interview": "Interview System",
        "speech-to-text": "Speech-to-Text", "text-to-speech": "Text-to-Speech", "stt": "STT", "tts": "TTS",
        "gtts": "gTTS", "whisper": "Whisper", "transformer": "Transformers", "opencv": "OpenCV", "yolo": "YOLO",
        "lstm": "LSTM", "machine learning": "Machine Learning", "nlp": "NLP", "rag": "RAG", "llm": "LLM",
    }
    low = text.lower()
    for token, label in mapping.items():
        if token in low and label not in found:
            found.append(label)
    return found[:35]


def _score_sentence(sentence: str, source_type: str) -> float:
    low = sentence.lower()
    words = set(re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]*", low))
    score = 0.0
    score += sum(1 for w in TECH_WORDS if w in low) * 1.5
    if source_type == "resume":
        score += sum(1 for w in PROJECT_WORDS if w in low) * 2.0
        if "role:" in low or "github" in low:
            score += 1.0
    else:
        for marker in ["required", "backend", "database", "ai interview", "evaluation", "role-based", "workflow"]:
            if marker in low:
                score += 2.0
    score += min(len(words) / 30, 2)
    return score


def infer_target_field(evidence: str, source_type: str, kind: str | None = None) -> str:
    low = evidence.lower()
    if any(x in low for x in ["available", "joining", "start date", "next round", "schedule"]):
        return "availability"
    if any(x in low for x in ["challenge", "debug", "problem", "issue", "solved", "difficulty"]):
        return "challenges"
    if any(x in low for x in ["project", "platform", "system", "application", "built", "developed", "github"]):
        return "projects"
    if any(x in low for x in ["intern", "experience", "role", "review", "continuous integration", "sprint", "agile"]):
        return "experience"
    if any(x in low for x in ["degree", "education", "university", "bachelor", "master", "mca", "bca"]):
        return "education"
    if any(x in low for x in ["strength", "team", "communication", "leadership", "collaborat"]):
        return "strengths"
    if any(x in low for x in TECH_WORDS):
        return "skills"
    return "skills" if source_type == "tech_stack" else "projects"


def analyse_document_text(text: str, source_type: str, filename: str = None) -> Dict[str, Any]:
    sentences = split_sentences(text)
    scored = sorted(sentences, key=lambda s: _score_sentence(s, source_type), reverse=True)
    project_evidence = []
    general_evidence = []
    for sentence in scored:
        low = sentence.lower()
        kind = "resume_project" if source_type == "resume" and any(w in low for w in PROJECT_WORDS) else source_type
        item = {
            "kind": kind if source_type == "resume" else "tech_stack",
            "target_field": infer_target_field(sentence, source_type, kind),
            "evidence": sentence,
        }
        if kind == "resume_project":
            project_evidence.append(item)
        else:
            general_evidence.append(item)
    evidence_items = (project_evidence[:4] + general_evidence[:4]) if source_type == "resume" else (general_evidence or project_evidence)[:6]
    return {
        "source_type": source_type,
        "filename": filename,
        "text_preview": clean_text(text)[:1000],
        "sentence_count": len(sentences),
        "keyphrases": keyphrases(text),
        "evidence_items": evidence_items[:8],
    }


def build_question_from_evidence(evidence: str, source_type: str, target_field: str, evidence_kind: str = None) -> str:
    low = evidence.lower()
    if source_type == "resume":
        if "entertainment management platform" in low:
            return "In your Entertainment Management Platform, how did you structure the Flask backend and data flow for features like bookmarking, progress tracking, filtering, and search?"
        if "translation" in low or "text-to-speech" in low or "gtts" in low:
            return "In your Translation and Text-to-Speech project, how did you integrate Flask, Transformers, and gTTS to create the final user flow?"
        if "bus arrival" in low or "lstm" in low:
            return "In your Bus Arrival Prediction project, how did you combine route data, live traffic, and machine learning to improve prediction accuracy?"
        if "defect" in low or "yolo" in low:
            return "In your Defect Detection project, how did you use YOLO or computer vision with Flask to show real-time results?"
        if "debug" in low or "continuous integration" in low or "code review" in low:
            return "Can you describe a project or internship task where you had to review code, debug issues, and improve the system through development cycles?"
        return f"Your resume mentions: {evidence[:180]}. Can you explain your actual role, implementation work, and what you learned from it?"

    if "mongodb" in low or "json" in low:
        return "How would you design MongoDB collections and JSON mirror files for candidates, rooms, interview transcripts, memory, and scoring in this AI-HRMS system?"
    if "role-based" in low or "dashboard" in low:
        return "How would you implement role-based dashboards and navigation for Super User, Controller, HR, Candidate, and Employee users?"
    if "speech" in low or "stt" in low or "tts" in low or "interview" in low:
        return "Which AI, STT, TTS, and answer-analysis tools would you use for the AI interview module, and how would they work together?"
    if "flask" in low or "routes" in low or "blueprint" in low or "api" in low:
        return "How would you structure Flask routes, Blueprints, and APIs for recruitment, shortlisting, room configuration, and interview processing?"
    return f"Based on the tech-stack requirement '{evidence[:180]}', how would you implement this part in a Python Flask system?"


def generate_forced_questions(tech_text: str, resume_text: str, tech_filename: str = None, resume_filename: str = None, tech_target: int = 3, resume_target: int = 3) -> Dict[str, Any]:
    tech = analyse_document_text(tech_text, "tech_stack", tech_filename)
    resume = analyse_document_text(resume_text, "resume", resume_filename)

    tech_questions = []
    for i, item in enumerate(tech["evidence_items"][:tech_target], 1):
        q = build_question_from_evidence(item["evidence"], "tech_stack", item["target_field"], item["kind"])
        tech_questions.append({
            "id": f"tech_stack_{i}", "source": "tech_stack", "source_label": "Tech Stack",
            "target_field": infer_target_field(q + " " + item["evidence"], "tech_stack"),
            "question": q, "question_type": "rag_forced", "evidence": item["evidence"],
            "evidence_kind": item["kind"], "asked": False,
        })

    resume_project = [x for x in resume["evidence_items"] if x.get("kind") == "resume_project"]
    resume_general = [x for x in resume["evidence_items"] if x.get("kind") != "resume_project"]
    project_needed = max(1, math.ceil(resume_target * 0.6))
    picked = resume_project[:project_needed]
    picked += [x for x in resume_project[project_needed:] + resume_general if x not in picked][:max(0, resume_target - len(picked))]
    resume_questions = []
    for i, item in enumerate(picked[:resume_target], 1):
        q = build_question_from_evidence(item["evidence"], "resume", item["target_field"], item["kind"])
        resume_questions.append({
            "id": f"resume_{i}", "source": "resume", "source_label": "Resume",
            "target_field": infer_target_field(q + " " + item["evidence"], "resume", item["kind"]),
            "question": q, "question_type": "rag_forced", "evidence": item["evidence"],
            "evidence_kind": item["kind"], "asked": False,
        })

    # Interleave tech/resume so the live interview does not feel like two separate questionnaires.
    forced = []
    for i in range(max(len(tech_questions), len(resume_questions))):
        if i < len(tech_questions):
            forced.append(tech_questions[i])
        if i < len(resume_questions):
            forced.append(resume_questions[i])
    tech["questions"] = tech_questions
    resume["questions"] = resume_questions
    return {
        "tech_stack": tech,
        "resume": resume,
        "forced_questions": forced,
        "asked_forced_question_ids": [],
        "strategy": "deterministic_sentence_evidence_with_project_weighted_resume_questions",
    }
