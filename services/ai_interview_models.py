"""Lazy model manager for the AI interview module.

The module deliberately avoids loading large ML models at Flask startup.  Models are
loaded only when RAG generation or an interview turn requires them.  The downloaded
weights remain in the normal Hugging Face/cache directories, while in-memory Python
objects can be released after the interview is completed.
"""

from __future__ import annotations

import gc
import os
import threading
from datetime import datetime, timezone
from typing import Dict, Any

try:
    import torch
except Exception:  # pragma: no cover - optional dependency for local JSON demo
    torch = None

from database.db import ai_interview_model_events_collection


def utcnow():
    return datetime.now(timezone.utc)


class AIInterviewModelManager:
    _lock = threading.RLock()
    _loading = False
    _last_error = None

    interviewer_tokenizer = None
    interviewer_model = None
    embedding_model = None
    stt_model = None
    grammar_tool = None

    interviewer_model_name = os.getenv("AI_INTERVIEW_CHAT_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
    embedding_model_name = os.getenv("AI_INTERVIEW_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    stt_model_size = os.getenv("AI_INTERVIEW_STT_MODEL", "tiny")

    @classmethod
    def status(cls) -> Dict[str, Any]:
        return {
            "loading": cls._loading,
            "last_error": cls._last_error,
            "loaded": {
                "chat": bool(cls.interviewer_model and cls.interviewer_tokenizer),
                "embedding": bool(cls.embedding_model),
                "stt": bool(cls.stt_model),
                "grammar": bool(cls.grammar_tool),
            },
            "model_names": {
                "chat": cls.interviewer_model_name,
                "embedding": cls.embedding_model_name,
                "stt": cls.stt_model_size,
            },
        }

    @classmethod
    def _event(cls, event_type: str, message: str, extra: Dict[str, Any] | None = None):
        try:
            ai_interview_model_events_collection.insert_one({
                "event_type": event_type,
                "message": message,
                "extra": extra or {},
                "created_at": utcnow(),
            })
        except Exception:
            pass

    @classmethod
    def load_embedding(cls):
        with cls._lock:
            if cls.embedding_model is not None:
                return cls.embedding_model
            cls._loading = True
            cls._event("load_start", "Loading AI interview embedding model", {"model": cls.embedding_model_name})
            try:
                from sentence_transformers import SentenceTransformer
                device = "cuda" if torch is not None and torch.cuda.is_available() else "cpu"
                cls.embedding_model = SentenceTransformer(cls.embedding_model_name, device=device)
                cls._last_error = None
                cls._event("load_done", "Embedding model loaded", {"device": device})
                return cls.embedding_model
            except Exception as exc:
                cls._last_error = str(exc)
                cls._event("load_failed", "Embedding model load failed", {"error": str(exc)})
                raise
            finally:
                cls._loading = False

    @classmethod
    def load_chat(cls):
        with cls._lock:
            if cls.interviewer_model is not None and cls.interviewer_tokenizer is not None:
                return cls.interviewer_tokenizer, cls.interviewer_model
            cls._loading = True
            cls._event("load_start", "Loading AI interview chat model", {"model": cls.interviewer_model_name})
            try:
                from transformers import AutoTokenizer, AutoModelForCausalLM
                cls.interviewer_tokenizer = AutoTokenizer.from_pretrained(cls.interviewer_model_name)
                dtype = torch.float16 if torch is not None and torch.cuda.is_available() else None
                kwargs = {"device_map": "auto"} if torch is not None and torch.cuda.is_available() else {}
                if dtype is not None:
                    kwargs["torch_dtype"] = dtype
                cls.interviewer_model = AutoModelForCausalLM.from_pretrained(cls.interviewer_model_name, **kwargs)
                if torch is None or not torch.cuda.is_available():
                    cls.interviewer_model.to("cpu")
                cls._last_error = None
                cls._event("load_done", "Chat model loaded", {"model": cls.interviewer_model_name})
                return cls.interviewer_tokenizer, cls.interviewer_model
            except Exception as exc:
                cls._last_error = str(exc)
                cls._event("load_failed", "Chat model load failed", {"error": str(exc)})
                raise
            finally:
                cls._loading = False

    @classmethod
    def load_for_rag(cls, use_chat: bool = False):
        embedding = cls.load_embedding()
        chat = cls.load_chat() if use_chat else None
        return {"embedding": embedding, "chat": chat}

    @classmethod
    def load_for_interview(cls, audio: bool = False, grammar: bool = True):
        loaded = {"embedding": cls.load_embedding(), "chat": None, "stt": None, "grammar": None}
        try:
            loaded["chat"] = cls.load_chat()
        except Exception:
            loaded["chat"] = None
        if grammar:
            loaded["grammar"] = cls.load_grammar()
        if audio:
            loaded["stt"] = cls.load_stt()
        return loaded

    @classmethod
    def load_stt(cls):
        with cls._lock:
            if cls.stt_model is not None:
                return cls.stt_model
            cls._loading = True
            cls._event("load_start", "Loading STT model", {"model": cls.stt_model_size})
            try:
                from faster_whisper import WhisperModel
                device = "cuda" if torch is not None and torch.cuda.is_available() else "cpu"
                compute_type = "float16" if device == "cuda" else "int8"
                cls.stt_model = WhisperModel(cls.stt_model_size, device=device, compute_type=compute_type)
                cls._last_error = None
                cls._event("load_done", "STT model loaded", {"device": device})
                return cls.stt_model
            except Exception as exc:
                cls._last_error = str(exc)
                cls._event("load_failed", "STT model load failed", {"error": str(exc)})
                raise
            finally:
                cls._loading = False

    @classmethod
    def load_grammar(cls):
        with cls._lock:
            if cls.grammar_tool is not None:
                return cls.grammar_tool
            try:
                import language_tool_python
                cls.grammar_tool = language_tool_python.LanguageTool("en-US")
                return cls.grammar_tool
            except Exception as exc:
                cls._last_error = str(exc)
                cls._event("load_failed", "Grammar tool load failed", {"error": str(exc)})
                return None

    @classmethod
    def unload_after_interview(cls):
        with cls._lock:
            cls._event("unload_start", "Unloading AI interview models from memory")
            cls.interviewer_tokenizer = None
            cls.interviewer_model = None
            cls.embedding_model = None
            cls.stt_model = None
            cls.grammar_tool = None
            gc.collect()
            if torch is not None and torch.cuda.is_available():
                torch.cuda.empty_cache()
            cls._event("unload_done", "AI interview models removed from memory; cached weights kept")
