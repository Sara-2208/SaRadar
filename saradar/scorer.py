"""Fit scoring (Phase 3B v2): Profile + JobRequirements -> explainable fit score.

Matching steps per requirement (best credit wins):
  1. exact      : word/alias found in skills or resume text   -> 1.00
  2. related    : known related concept found (CV <- CNN)     -> 0.85
  3. overlap    : all key words in one resume line            -> 0.85
                  half or more key words in one line          -> 0.50
  4. embeddings : meaning similarity >= 0.55 -> 0.85, >= 0.40 -> 0.50

All numbers are computed in code. The LLM only writes explain_fit().
Scored for an entry-level candidate who does not want internships.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from saradar import llm as llm_mod
from saradar.config import load_preferences
from saradar.schemas import JobRequirements, Profile

logger = logging.getLogger("saradar.scorer")

DEFAULT_WEIGHTS = {
    "must_have": 0.40,
    "similarity": 0.20,
    "seniority": 0.20,
    "nice_to_have": 0.10,
    "location": 0.10,
}
EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

ALIASES = {
    "ml": "machine learning", "ai": "artificial intelligence",
    "genai": "generative ai", "gen ai": "generative ai",
    "llm": "large language models", "llms": "large language models",
    "nlp": "natural language processing", "cv": "computer vision",
    "rag": "retrieval-augmented generation", "postgres": "postgresql",
    "sklearn": "scikit-learn", "powerbi": "power bi", "k8s": "kubernetes",
    "js": "javascript", "gcp": "google cloud",
}

# Requirement (normalized) -> resume terms that count as strong evidence
RELATED = {
    "computer vision": ["cnn", "convolutional neural network", "image classification",
                        "object detection", "opencv", "yolo", "image processing"],
    "generative ai": ["llm", "large language models", "llm integration", "chatbot", "gpt",
                      "prompt engineering", "ai agent"],
    "retrieval-augmented generation": ["retrieval", "vector database", "embeddings",
                                       "semantic search", "llamaindex"],
    "model deployment": ["deployed", "deployment", "docker", "mlflow", "model endpoints",
                         "fastapi", "kubernetes"],
    "api integration": ["api", "apis", "rest api", "postman", "endpoints", "webhook"],
    "data preparation": ["data cleaning", "preprocessing", "data wrangling",
                         "feature engineering", "etl"],
    "structured data analysis": ["sql", "data analysis", "power bi", "pandas", "excel"],
    "data analysis": ["sql", "power bi", "pandas", "statistics", "data visualization"],
    "mlops": ["mlflow", "docker", "ci/cd", "model deployment"],
    "automation": ["n8n", "workflow automation", "ai automation", "zapier"],
    "ai agents": ["ai agent workflows", "agentic", "tool calling", "langgraph", "n8n"],
    "cloud": ["aws", "azure", "gcp", "google cloud", "virtual machines"],
    "deep learning": ["cnn", "neural network", "pytorch", "tensorflow"],
}

_STOP = {
    "and", "or", "the", "of", "for", "with", "in", "on", "to", "a", "an", "using",
    "skills", "skill", "experience", "knowledge", "strong", "good", "ability",
    "proficiency", "solid", "hands", "working", "familiarity",
}

KLANG_VALLEY = [
    "kuala lumpur", "kl", "selangor", "putrajaya", "petaling jaya", "pj",
    "puchong", "cyberjaya", "shah alam", "subang", "klang", "bangsar",
    "mont kiara", "damansara", "cheras", "trx",
]

_LEVEL_SCORE = {  # candidate with ~0 years who does NOT want internships
    "intern": 0.4, "entry": 1.0, "junior": 1.0, "mid": 0.4,
    "senior": 0.15, "lead": 0.1, "manager": 0.05,
}
_TITLE_LEVEL = [
    (r"\b(head|director|principal|vp)\b", "manager"),
    (r"\bmanager\b", "manager"),
    (r"\blead\b", "lead"),
    (r"\b(senior|sr)\b", "senior"),
    (r"\b(intern|internship|trainee)\b", "intern"),
    (r"\b(junior|jr|graduate|fresh)\b", "entry"),
]


# ---------------------------------------------------------------------------
# Embeddings (lazy; replaceable in tests)
# ---------------------------------------------------------------------------

_embedder: Optional[Callable[[Sequence[str]], np.ndarray]] = None


def _get_embedder() -> Callable[[Sequence[str]], np.ndarray]:
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(EMBED_MODEL_NAME)
        _embedder = lambda texts: model.encode(  # noqa: E731
            list(texts), normalize_embeddings=True, convert_to_numpy=True
        )
    return _embedder


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class SkillMatch:
    requirement: str
    kind: str                      # exact / similar / partial / missing
    credit: float
    evidence: Optional[str] = None
    similarity: Optional[float] = None
    method: Optional[str] = None   # exact / related / overlap / embedding


@dataclass
class FitResult:
    score: int
    label: str
    breakdown: Dict[str, int]
    must_have: List[SkillMatch]
    nice_to_have: List[SkillMatch]
    confidence: str
    notes: List[str] = field(default_factory=list)

    @property
    def matched(self) -> List[str]:
        return [m.requirement for m in self.must_have if m.kind in ("exact", "similar")]

    @property
    def partial(self) -> List[str]:
        return [m.requirement for m in self.must_have if m.kind == "partial"]

    @property
    def missing(self) -> List[str]:
        return [m.requirement for m in self.must_have if m.kind == "missing"]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.update(matched=self.matched, partial=self.partial, missing=self.missing)
        return d


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def _norm(s: str) -> str:
    s = re.sub(r"[^a-z0-9+#.\-/ ]", " ", (s or "").lower())
    s = re.sub(r"\s+", " ", s).strip()
    return ALIASES.get(s, s)


def _norm_text(text: str) -> str:
    """Lowercase text plus alias expansions (LLM -> large language models)."""
    t = re.sub(r"[^a-z0-9+#.\-/\n ]", " ", text.lower())
    t = re.sub(r"[ \t]+", " ", t)
    extra = [full for short, full in ALIASES.items() if re.search(rf"\b{re.escape(short)}\b", t)]
    return t + "\n" + "\n".join(extra)


def _contains(needle: str, haystack: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack) is not None


def _tokens(s: str) -> List[str]:
    out = []
    for t in re.findall(r"[a-z0-9+#]+", (s or "").lower()):
        if t in _STOP or len(t) < 2:
            continue
        if len(t) > 3 and t.endswith("s"):
            t = t[:-1]
        out.append(t)
    return out


def _tok_eq(a: str, b: str) -> bool:
    """Same word or same 5-letter stem (deployment ~ deployed, analysis ~ analytics)."""
    return a == b or (len(a) >= 5 and len(b) >= 5 and a[:5] == b[:5])


def _evidence(profile: Profile) -> List[str]:
    lines: List[str] = []
    lines += profile.skills.technical + profile.skills.tools + profile.skills.soft
    lines += [x for x in (profile.headline, profile.summary) if x]
    for e in profile.experience:
        lines.append(" ".join(filter(None, [e.title, "at", e.company])))
        lines += e.bullets
    for p in profile.projects:
        lines.append(" ".join(filter(None, [p.name, p.description])))
        lines += p.tech
    for ed in profile.education:
        lines.append(" ".join(filter(None, [ed.degree, ed.field])))
        lines += ed.bullets
    for a in profile.activities:
        lines += a.bullets
    lines += profile.certifications
    return [ln.strip() for ln in lines if ln and ln.strip()]


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def _related_match(n: str, ev_norm: List[str], ev_lines: List[str]) -> Optional[str]:
    for term in RELATED.get(n, []):
        for line, low in zip(ev_lines, ev_norm):
            if _contains(term, low):
                return line
    return None


def _overlap_match(req: str, ev_toks: List[List[str]], ev_lines: List[str]) -> Tuple[float, Optional[str]]:
    req_toks = _tokens(req)
    if not req_toks:
        return 0.0, None
    best, best_line = 0.0, None
    for line, toks in zip(ev_lines, ev_toks):
        hits = sum(1 for r in req_toks if any(_tok_eq(r, t) for t in toks))
        frac = hits / len(req_toks)
        if frac > best:
            best, best_line = frac, line
    if best >= 1.0:
        return 0.85, best_line
    if best >= 0.5:
        return 0.5, best_line
    return 0.0, None


def _match(
    requirements: List[str],
    skills_norm: set,
    text_norm: str,
    ev_lines: List[str],
    ev_norm: List[str],
    ev_toks: List[List[str]],
    ev_vecs: np.ndarray,
    embed: Callable,
) -> List[SkillMatch]:
    results: List[Optional[SkillMatch]] = []
    pending: List[Tuple[int, str, float, Optional[str]]] = []

    for req in requirements:
        n = _norm(req)
        # 1. exact
        if n and (n in skills_norm or _contains(n, text_norm)):
            ev = next((ln for ln, low in zip(ev_lines, ev_norm) if _contains(n, low)), None)
            results.append(SkillMatch(req, "exact", 1.0, evidence=ev, method="exact"))
            continue
        # 2. related concept
        rel = _related_match(n, ev_norm, ev_lines)
        if rel:
            results.append(SkillMatch(req, "similar", 0.85, evidence=rel, method="related"))
            continue
        # 3. word overlap (kept as a candidate; embeddings may do better)
        ov_credit, ov_line = _overlap_match(req, ev_toks, ev_lines)
        pending.append((len(results), req, ov_credit, ov_line))
        results.append(None)

    # 4. embeddings for everything still pending
    if pending and len(ev_lines):
        req_vecs = np.asarray(embed([p[1] for p in pending]))
        sims = req_vecs @ ev_vecs.T
        for row, (idx, req, ov_credit, ov_line) in enumerate(pending):
            j = int(np.argmax(sims[row]))
            s = round(float(sims[row][j]), 2)
            emb_credit = 0.85 if s >= 0.55 else 0.5 if s >= 0.40 else 0.0
            if ov_credit >= emb_credit and ov_credit > 0:
                credit, line, method = ov_credit, ov_line, "overlap"
            else:
                credit, line, method = emb_credit, ev_lines[j], "embedding"
            kind = "similar" if credit >= 0.85 else "partial" if credit > 0 else "missing"
            results[idx] = SkillMatch(req, kind, credit, line if credit > 0 else None, s, method)

    return [r for r in results if r is not None]


# ---------------------------------------------------------------------------
# Seniority + location + label
# ---------------------------------------------------------------------------


def _years_score(required: Optional[int], candidate: int = 0) -> Optional[float]:
    """Score by the gap between required years and the candidate's years."""
    if required is None:
        return None
    gap = required - candidate
    if gap <= 0:
        return 1.0
    if gap == 1:
        return 0.6
    if gap == 2:
        return 0.25
    if gap == 3:
        return 0.1
    return 0.05


def _seniority(req: JobRequirements, candidate_years: int = 0) -> Tuple[float, Optional[str]]:
    scores: List[float] = []
    note = None
    level = (req.seniority or "").strip().lower()
    if level in _LEVEL_SCORE:
        scores.append(_LEVEL_SCORE[level])
    title = (req.title or "").lower()
    for pattern, lvl in _TITLE_LEVEL:
        if re.search(pattern, title):
            scores.append(_LEVEL_SCORE[lvl])
            break
    ys = _years_score(req.years_experience_min, candidate_years)
    if ys is not None:
        scores.append(ys)
        if req.years_experience_min and req.years_experience_min > candidate_years:
            note = (f"Asks for {req.years_experience_min}+ years of experience "
                    f"(you have {candidate_years})")
    return (min(scores) if scores else 0.75), note


def _location(req: JobRequirements, prefs: Dict[str, Any]) -> Tuple[float, Optional[str]]:
    if req.work_mode and "remote" in req.work_mode.lower():
        return 1.0, None
    if not req.location:
        return 0.7, "Location not stated"
    loc = req.location.lower()
    areas = [a.lower() for a in prefs.get("areas", [])] + KLANG_VALLEY
    if any(_contains(a, loc) for a in areas):
        return 1.0, None
    return 0.3, f"Outside preferred areas ({req.location})"


def _label(score: int, seniority_score: float) -> Tuple[str, Optional[str]]:
    """Score label; roles above entry level are capped at 'Fair fit'."""
    label = "Strong fit" if score >= 75 else "Fair fit" if score >= 55 else "Stretch"
    if label == "Strong fit" and seniority_score < 0.6:
        return "Fair fit", "Capped at Fair fit: role needs more experience than entry level"
    return label, None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def score_fit(
    profile: Profile,
    req: JobRequirements,
    jd_text: Optional[str] = None,
    preferences: Optional[Dict[str, Any]] = None,
) -> FitResult:
    """Compute an explainable 0-100 fit score."""
    prefs = preferences if preferences is not None else load_preferences()
    weights = {**DEFAULT_WEIGHTS, **(prefs.get("fit_weights") or {})}
    embed = _get_embedder()

    ev_lines = _evidence(profile)
    if not ev_lines:
        raise ValueError("Profile is empty. Parse and save your resume first.")

    ev_norm = [_norm_text(ln) for ln in ev_lines]
    ev_toks = [_tokens(ln) for ln in ev_lines]
    skills_norm = {_norm(s) for s in profile.all_skills()}
    text_norm = _norm_text("\n".join(ev_lines))
    ev_vecs = np.asarray(embed(ev_lines))

    args = (skills_norm, text_norm, ev_lines, ev_norm, ev_toks, ev_vecs, embed)
    must = _match(req.must_have_skills, *args)
    nice = _match(req.nice_to_have_skills, *args)
    notes: List[str] = []

    job_text = jd_text or "\n".join(
        [req.title or "", *req.must_have_skills, *req.nice_to_have_skills, *req.responsibilities]
    )
    prof_text = "\n".join(filter(None, [profile.headline, profile.summary, ", ".join(profile.all_skills())]))
    vecs = np.asarray(embed([prof_text or "\n".join(ev_lines[:20]), job_text[:2000]]))
    sim_score = _clip((float(vecs[0] @ vecs[1]) - 0.30) / 0.40)

    if must:
        must_score = sum(m.credit for m in must) / len(must)
    else:
        must_score = sim_score
        notes.append("No clear must-have skills listed; used overall similarity instead")
    nice_score = sum(m.credit for m in nice) / len(nice) if nice else 0.75

    candidate_years = int(prefs.get("candidate_years_experience", 0))
    sen_score, sen_note = _seniority(req, candidate_years)
    loc_score, loc_note = _location(req, prefs)
    notes += [n for n in (sen_note, loc_note) if n]

    components = {
        "must_have": must_score,
        "similarity": sim_score,
        "seniority": sen_score,
        "nice_to_have": nice_score,
        "location": loc_score,
    }
    total = sum(weights[k] * v for k, v in components.items()) / sum(weights[k] for k in components)
    score = round(total * 100)

    # Experience-gap caps: skills can't hide a big experience gap
    if req.years_experience_min is not None:
        gap = req.years_experience_min - candidate_years
        if gap >= 2:
            score = min(score, 45)
            notes.append(f"Capped: {gap} years more experience required than you have")
        elif gap == 1:
            score = min(score, 74)
    label, cap_note = _label(score, sen_score)
    if cap_note:
        notes.append(cap_note)

    confidence = "high"
    if req.jd_quality == "partial":
        confidence = "low"
        notes.append("Job description is only a short summary; score is rough")
    elif not req.must_have_skills:
        confidence = "low"

    return FitResult(
        score=score,
        label=label,
        breakdown={k: round(v * 100) for k, v in components.items()},
        must_have=must,
        nice_to_have=nice,
        confidence=confidence,
        notes=notes,
    )


def _template_explanation(fit: FitResult) -> str:
    parts = [f"{fit.label} ({fit.score}%)."]
    if fit.matched:
        parts.append(f"Strong matches: {', '.join(fit.matched[:5])}.")
    if fit.missing:
        parts.append(f"Gaps: {', '.join(fit.missing[:5])}.")
    if fit.notes:
        parts.append(fit.notes[0] + ".")
    return " ".join(parts)


def explain_fit(fit: FitResult, req: JobRequirements) -> str:
    """2 to 3 sentence explanation written by the LLM from computed data only."""
    payload = {
        "job_title": req.title,
        "seniority": req.seniority,
        "years_required": req.years_experience_min,
        "score": fit.score,
        "label": fit.label,
        "matched": fit.matched,
        "partial": fit.partial,
        "missing": fit.missing,
        "nice_to_have_matched": [m.requirement for m in fit.nice_to_have if m.kind != "missing"],
        "notes": fit.notes,
        "confidence": fit.confidence,
    }
    system = (
        "You are a friendly career coach. In 2 to 3 short sentences, explain this "
        "job fit score to the candidate. Use ONLY the data provided; never add skills, "
        "claims or numbers that are not in it. Mention the strongest matches and the "
        "most important gaps. If the notes mention years of experience, seniority or "
        "location, mention that briefly too. Plain text, no markdown, no bullet points."
    )
    try:
        result = llm_mod.complete(json.dumps(payload), system=system, tier="smart")
        return result.text.strip() or _template_explanation(fit)
    except llm_mod.AllModelsFailed:
        return _template_explanation(fit)