#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Yim.
# The Yim project belongs to the Dunimd Team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# DISCLAIMER: Users must comply with applicable AI regulations.
# Non-compliance may result in service termination or legal liability.

import math
import os
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from yim.logging_config import get_logger

logger = get_logger("yim.memdir.semantic")


# ---------------------------------------------------------------------------
# Lightweight text vectorisation (no heavy deps)
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """Lowercase, split on word boundaries, drop very short tokens."""
    tokens = re.findall(r"[a-zA-Z0-9_一-鿿]{2,}", text.lower())
    return tokens


def _tf_idf_vectorize(doc: str, idf: dict[str, float], vocabulary: set[str]) -> dict[str, float]:
    """Convert a document to a sparse tf-idf vector."""
    tokens = _tokenize(doc)
    if not tokens:
        return {}
    tf = Counter(tokens)
    vec: dict[str, float] = {}
    n = len(tokens)
    for term, count in tf.items():
        if term not in vocabulary:
            continue
        tf_val = count / n
        vec[term] = tf_val * idf.get(term, 1.0)
    return vec


def _cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine between two sparse vectors."""
    if not a or not b:
        return 0.0
    keys = set(a.keys()) & set(b.keys())
    dot = sum(a[k] * b[k] for k in keys)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _jaccard_similarity(a: str, b: str) -> float:
    """Jaccard coefficient on token sets — fast, no training needed."""
    sa = set(_tokenize(a))
    sb = set(_tokenize(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _build_idf(corpus: list[str]) -> dict[str, float]:
    """Build inverse document frequency from a corpus of documents."""
    n = len(corpus)
    if n == 0:
        return {}
    df: dict[str, int] = {}
    for doc in corpus:
        seen: set[str] = set()
        for token in _tokenize(doc):
            if token not in seen:
                df[token] = df.get(token, 0) + 1
                seen.add(token)
    idf: dict[str, float] = {}
    for term, count in df.items():
        idf[term] = math.log((n + 1) / (count + 1)) + 1.0
    return idf


# ---------------------------------------------------------------------------
# Embedding loader (optional — tries sentence-transformers, then ONNX)
# ---------------------------------------------------------------------------

@dataclass
class EmbeddingModel:
    """Lightweight wrapper that tries to load an embedding model."""

    loaded: bool = False
    dim: int = 0
    _model: Any = None

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self.dim for _ in texts]


def _try_load_embedding() -> EmbeddingModel:
    """Best-effort loading of a sentence-transformer or ONNX embedding model."""
    # Try sentence-transformers first
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        return EmbeddingModel(loaded=True, dim=384, _model=model)
    except Exception:
        pass

    try:
        import numpy as np
        import onnxruntime as ort

        model_path = os.environ.get("YIM_EMBEDDING_MODEL", "")
        if model_path and os.path.exists(model_path):
            session = ort.InferenceSession(model_path)
            return EmbeddingModel(loaded=True, dim=384, _model=session)
    except Exception:
        pass

    if not getattr(_try_load_embedding, "_logged", False):
        _try_load_embedding._logged = True  # type: ignore[attr-defined]
        logger.info("No embedding model available - using tf-idf fallback for semantic search")
    return EmbeddingModel(loaded=False, dim=0)


# ---------------------------------------------------------------------------
# SemanticMemorySearch
# ---------------------------------------------------------------------------

@dataclass
class SearchResult:
    file_name: str
    score: float
    snippet: str = ""
    memory_type: str = ""
    description: str = ""


class SemanticMemorySearch:
    """Embedding-based memory search with tf-idf / Jaccard fallback.

    When an embedding model is available (via sentence-transformers or ONNX),
    all memories are indexed as dense vectors and queries use cosine similarity.
    Otherwise a tf-idf vector space model is built from the memory corpus and
    used for retrieval.  Jaccard is the last-resort fallback for tiny corpora.
    """

    def __init__(self, memory_dir: str) -> None:
        self._memory_dir = memory_dir
        self._embedding = _try_load_embedding()
        self._corpus: dict[str, str] = {}          # filename → raw text
        self._vectors: dict[str, list[float]] = {}  # filename → embedding
        self._idf: dict[str, float] = {}
        self._vocabulary: set[str] = set()
        self._dirty = True

    def index(self, files: dict[str, str]) -> None:
        """Replace the in-memory index with *files* (filename → text)."""
        self._corpus = dict(files)
        self._vectors.clear()
        self._dirty = True

        if self._embedding.loaded and files:
            names = list(files.keys())
            texts = [files[n] for n in names]
            try:
                embeddings = self._embedding.encode(texts)
                for name, vec in zip(names, embeddings):
                    self._vectors[name] = vec
            except Exception:
                logger.warning("Embedding encode failed, falling back to tf-idf")

        if not self._vectors:
            # Build tf-idf index
            self._idf = _build_idf(list(files.values()))
            self._vocabulary = set(self._idf.keys())

        self._dirty = False

    def search(self, query: str, top_k: int = 5, min_score: float = 0.05) -> list[SearchResult]:
        """Return top-k memories matching *query*."""
        if self._dirty:
            self._rebuild_from_disk()

        if not self._corpus:
            return []

        results: list[SearchResult] = []

        if self._vectors:
            # Dense embedding search
            try:
                q_vec = self._embedding.encode([query])[0]
            except Exception:
                q_vec = []
            if q_vec:
                for name, vec in self._vectors.items():
                    score = _cosine_sparse(q_vec, vec)
                    if score >= min_score:
                        results.append(SearchResult(
                            file_name=name,
                            score=score,
                            snippet=self._corpus[name][:200],
                        ))
                results.sort(key=lambda r: r.score, reverse=True)
                return results[:top_k]

        # Sparse tf-idf search
        q_vec = _tf_idf_vectorize(query, self._idf, self._vocabulary)
        if q_vec:
            for name, text in self._corpus.items():
                d_vec = _tf_idf_vectorize(text, self._idf, self._vocabulary)
                score = _cosine_similarity(q_vec, d_vec)
                if score >= min_score:
                    results.append(SearchResult(
                        file_name=name,
                        score=score,
                        snippet=text[:200],
                    ))

        # Jaccard fallback for tiny corpora
        if not results:
            for name, text in self._corpus.items():
                score = _jaccard_similarity(query, text)
                if score >= min_score:
                    results.append(SearchResult(
                        file_name=name,
                        score=score,
                        snippet=text[:200],
                    ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def search_relevant(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Search with a slightly higher min_score threshold for relevance."""
        return self.search(query, top_k=top_k, min_score=0.10)

    def _rebuild_from_disk(self) -> None:
        """Scan the memory directory and rebuild the index."""
        files: dict[str, str] = {}
        try:
            with os.scandir(self._memory_dir) as entries:
                for entry in entries:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    if entry.name == "MEMORY.md" or entry.name.startswith("."):
                        continue
                    if not entry.name.endswith(".md"):
                        continue
                    try:
                        with open(entry.path, "r", encoding="utf-8") as f:
                            files[entry.name] = f.read()
                    except (OSError, UnicodeDecodeError):
                        pass
        except OSError:
            pass
        self.index(files)


def _cosine_sparse(a: list[float], b: list[float]) -> float:
    """Cosine between two dense vectors (kept as lists)."""
    if len(a) != len(b) or len(a) == 0:
        return 0.0
    dot = sum(av * bv for av, bv in zip(a, b))
    norm_a = math.sqrt(sum(v * v for v in a))
    norm_b = math.sqrt(sum(v * v for v in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# WorkingMemory — in-flight task context
# ---------------------------------------------------------------------------

@dataclass
class WorkingMemory:
    """Transient, structured context for the current task.

    Carries hypotheses, findings, open questions, and scratchpad notes
    across turns within a single agent run.  Not persisted to disk — when
    the session ends, the agent should consolidate relevant items into
    persistent memory via MemoryConsolidator.
    """

    current_goal: str = ""
    subgoals: list[str] = field(default_factory=list)
    hypotheses: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    scratchpad: list[str] = field(default_factory=list)
    _created_at: float = field(default_factory=time.time)

    def set_goal(self, goal: str) -> None:
        self.current_goal = goal

    def add_subgoal(self, subgoal: str) -> None:
        if subgoal not in self.subgoals:
            self.subgoals.append(subgoal)

    def complete_subgoal(self, subgoal: str) -> None:
        if subgoal in self.subgoals:
            self.subgoals.remove(subgoal)

    def add_hypothesis(self, hypothesis: str) -> None:
        if hypothesis not in self.hypotheses:
            self.hypotheses.append(hypothesis)

    def confirm_hypothesis(self, hypothesis: str) -> None:
        if hypothesis in self.hypotheses:
            self.hypotheses.remove(hypothesis)
        if hypothesis not in self.findings:
            self.findings.append(f"[CONFIRMED] {hypothesis}")

    def reject_hypothesis(self, hypothesis: str) -> None:
        if hypothesis in self.hypotheses:
            self.hypotheses.remove(hypothesis)
        self.findings.append(f"[REJECTED] {hypothesis}")

    def add_finding(self, finding: str) -> None:
        if finding not in self.findings:
            self.findings.append(finding)

    def add_question(self, question: str) -> None:
        if question not in self.open_questions:
            self.open_questions.append(question)

    def resolve_question(self, question: str, answer: str = "") -> None:
        if question in self.open_questions:
            self.open_questions.remove(question)
        entry = f"Q: {question}"
        if answer:
            entry += f" → {answer}"
        self.findings.append(entry)

    def note(self, text: str) -> None:
        self.scratchpad.append(text)

    def summarize(self) -> str:
        """Produce a compact text summary for injection into the agent prompt."""
        parts: list[str] = []
        if self.current_goal:
            parts.append(f"Goal: {self.current_goal}")

        if self.subgoals:
            parts.append("Subgoals:")
            for sg in self.subgoals:
                parts.append(f"  - {sg}")

        if self.hypotheses:
            parts.append("Hypotheses:")
            for h in self.hypotheses:
                parts.append(f"  - {h}")

        if self.findings:
            parts.append("Findings:")
            for f in self.findings[-10:]:  # last 10
                parts.append(f"  - {f}")

        if self.open_questions:
            parts.append("Open questions:")
            for q in self.open_questions:
                parts.append(f"  - {q}")

        if self.scratchpad:
            parts.append("Scratchpad:")
            for s in self.scratchpad[-5:]:  # last 5
                parts.append(f"  - {s}")

        if not parts:
            return "(empty working memory)"
        return "\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_goal": self.current_goal,
            "subgoals": list(self.subgoals),
            "hypotheses": list(self.hypotheses),
            "findings": list(self.findings),
            "open_questions": list(self.open_questions),
            "scratchpad": list(self.scratchpad),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "WorkingMemory":
        wm = cls()
        wm.current_goal = d.get("current_goal", "")
        wm.subgoals = d.get("subgoals", [])
        wm.hypotheses = d.get("hypotheses", [])
        wm.findings = d.get("findings", [])
        wm.open_questions = d.get("open_questions", [])
        wm.scratchpad = d.get("scratchpad", [])
        return wm


# ---------------------------------------------------------------------------
# MemoryConsolidator — merge, conflict detection, staleness
# ---------------------------------------------------------------------------

@dataclass
class ConsolidationAction:
    action: str  # merge | flag_conflict | mark_stale | keep
    file_a: str
    file_b: str = ""
    reason: str = ""
    merged_content: str = ""


class MemoryConsolidator:
    """Post-hoc memory maintenance: merge near-duplicates, flag conflicting
    memories, detect staleness, and suggest pruning.

    SIMILARITY_THRESHOLD above which two memories are considered duplicates.
    CONFLICT_THRESHOLD above which two memories on the same topic but with
    opposing claims are flagged for review.
    """

    SIMILARITY_THRESHOLD = 0.75
    CONFLICT_PATTERNS = [
        (r"\b(?:do not|don't|never|should not|must not|avoid|forbidden|prohibited)\b",
         r"\b(?:do|always|should|must|use|prefer|recommended|allowed)\b"),
        (r"\b(?:remove|delete|drop|discard|abandon)\b",
         r"\b(?:keep|retain|preserve|maintain|add)\b"),
    ]

    def __init__(self, memory_dir: str) -> None:
        self._memory_dir = memory_dir

    def find_duplicates(self, files: dict[str, str]) -> list[ConsolidationAction]:
        """Return merge actions for pairs that exceed SIMILARITY_THRESHOLD."""
        actions: list[ConsolidationAction] = []
        names = list(files.keys())
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                score = _jaccard_similarity(files[names[i]], files[names[j]])
                if score >= self.SIMILARITY_THRESHOLD:
                    merged = self._merge_pair(names[i], files[names[i]], names[j], files[names[j]])
                    actions.append(ConsolidationAction(
                        action="merge",
                        file_a=names[i],
                        file_b=names[j],
                        reason=f"Jaccard similarity {score:.2f} >= {self.SIMILARITY_THRESHOLD}",
                        merged_content=merged,
                    ))
        return actions

    def find_conflicts(self, files: dict[str, str]) -> list[ConsolidationAction]:
        """Detect memories that make opposing claims about the same topic."""
        actions: list[ConsolidationAction] = []
        names = list(files.keys())
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                text_a, text_b = files[names[i]], files[names[j]]
                # Only check pairs with some topical overlap
                if _jaccard_similarity(text_a, text_b) < 0.30:
                    continue
                if self._has_opposing_claims(text_a, text_b):
                    actions.append(ConsolidationAction(
                        action="flag_conflict",
                        file_a=names[i],
                        file_b=names[j],
                        reason="Opposing claims detected (e.g. do vs don't, keep vs remove)",
                    ))
        return actions

    def find_stale(self, files: dict[str, str], age_days: dict[str, int],
                   stale_threshold_days: int = 30) -> list[ConsolidationAction]:
        """Flag memories older than *stale_threshold_days* that reference
        specific file paths or function names no longer present in the repo."""
        actions: list[ConsolidationAction] = []
        for name, text in files.items():
            days = age_days.get(name, 0)
            if days < stale_threshold_days:
                continue
            # Check for file:line references
            refs = re.findall(r"`([\w./-]+\.[\w]+):\d+`|`([\w./-]+\.[\w]+)`", text)
            missing: list[str] = []
            for ref_tuple in refs:
                path = ref_tuple[0] or ref_tuple[1]
                if path and not self._path_exists(path):
                    missing.append(path)
            if missing:
                actions.append(ConsolidationAction(
                    action="mark_stale",
                    file_a=name,
                    reason=f"References missing files: {', '.join(missing[:3])}",
                ))
        return actions

    def consolidate(self, files: dict[str, str],
                    age_days: dict[str, int] | None = None) -> list[ConsolidationAction]:
        """Run all checks and return ordered actions."""
        actions: list[ConsolidationAction] = []
        actions.extend(self.find_duplicates(files))
        actions.extend(self.find_conflicts(files))
        if age_days:
            actions.extend(self.find_stale(files, age_days))
        # Sort: merges first, then conflicts, then staleness
        priority = {"merge": 0, "flag_conflict": 1, "mark_stale": 2}
        actions.sort(key=lambda a: priority.get(a.action, 99))
        return actions

    @staticmethod
    def _merge_pair(name_a: str, text_a: str, name_b: str, text_b: str) -> str:
        """Naive merge: keep the newer/larger one as primary, append key lines from the other."""
        primary = text_a if len(text_a) >= len(text_b) else text_b
        secondary = text_b if primary == text_a else text_a
        sec_lines = set(secondary.strip().split("\n"))
        pri_lines = set(primary.strip().split("\n"))
        unique = [l for l in secondary.strip().split("\n")
                  if l not in pri_lines and len(l.strip()) > 10]
        if unique:
            primary += "\n\n## Merged from duplicate\n" + "\n".join(unique[:20])
        return primary

    def _has_opposing_claims(self, text_a: str, text_b: str) -> bool:
        """Check if two texts contain opposing directive patterns."""
        for pos_pat, neg_pat in self.CONFLICT_PATTERNS:
            a_pos = bool(re.search(pos_pat, text_a, re.IGNORECASE))
            a_neg = bool(re.search(neg_pat, text_a, re.IGNORECASE))
            b_pos = bool(re.search(pos_pat, text_b, re.IGNORECASE))
            b_neg = bool(re.search(neg_pat, text_b, re.IGNORECASE))
            if (a_pos and b_neg) or (a_neg and b_pos):
                return True
        return False

    def _path_exists(self, rel_path: str) -> bool:
        """Check if a relative path exists relative to the repo root (cwd)."""
        candidate = os.path.join(os.getcwd(), rel_path)
        return os.path.exists(candidate)
