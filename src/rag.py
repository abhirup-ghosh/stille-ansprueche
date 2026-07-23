"""Phase 4a: the grounded RAG answer pipeline over 3 prompt variants."""
import time

from langdetect import detect
from pydantic import BaseModel

from src import config
from src.llm import LLMClient
from src.search import search_best

SHARED_GROUNDING_RULES = """\
REGELN:
- Antworte AUSSCHLIESSLICH auf Basis des bereitgestellten KONTEXT.
- Erfinde NIEMALS Geldbeträge, Fristen oder Anspruchsvoraussetzungen. Wenn der Kontext eine
  Information nicht enthält, sage das ausdrücklich.
- Nenne für jede erwähnte Leistung die Rechtsgrundlage und, falls vorhanden, den offiziellen Link.
- Antworte in der Sprache der Frage (Deutsch oder Englisch).
- Schließe mit dem Hinweis ab, dass dies keine Rechtsberatung ist und die zuständige Behörde
  verbindliche Auskunft gibt.
"""

PROMPT_V1 = SHARED_GROUNDING_RULES + "\nBeantworte die Frage der Person hilfreich und korrekt."

PROMPT_V2 = SHARED_GROUNDING_RULES + """
Antworte in Einfacher Sprache: kurze Sätze (max. ~12 Wörter), keine Fachbegriffe ohne Erklärung,
direkte Ansprache, konkrete nächste Schritte als nummerierte Liste."""

PROMPT_V3 = SHARED_GROUNDING_RULES + """
Strukturiere die Antwort: (1) Kurzantwort in 2 Sätzen, (2) 'Diese Leistungen kommen in Frage'
als Liste mit je 1 Satz Begründung, (3) 'Nächste Schritte', (4) 'Quellen'."""

PROMPT_VARIANTS = {
    "baseline": PROMPT_V1,
    "einfache_sprache": PROMPT_V2,
    "structured": PROMPT_V3,
}

# Phase 4b LLM evaluation winner (highest %faithful over 100 sampled questions x 3 variants):
# einfache_sprache, 57% faithful vs. 41% (baseline) / 36% (structured). See
# data/eval/rag_results.csv and the README's "RAG evaluation" section for the full comparison.
PROMPT_VBEST = "einfache_sprache"

_llm_client: LLMClient | None = None


def _get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


class RagAnswer(BaseModel):
    answer: str
    benefits_mentioned: list[str]
    sources: list[dict]
    model: str
    prompt_variant: str
    response_time_s: float
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


class _RagLLMOutput(BaseModel):
    answer: str
    benefits_mentioned: list[str]


def _build_context_block(hits: list[dict]) -> str:
    sections = []
    for hit in hits:
        link = hit.get("official_url") or "siehe zuständige Behörde"
        sections.append(f"## {hit['name']}\nRechtsgrundlage: {hit['legal_norm']}\n{hit['text']}\nOffizieller Link: {link}")
    return "\n\n".join(sections)


def answer(question: str, prompt_variant: str = "v_best", k: int = 5) -> RagAnswer:
    variant_key = PROMPT_VBEST if prompt_variant == "v_best" else prompt_variant
    system_prompt = PROMPT_VARIANTS[variant_key]

    try:
        lang = detect(question)
    except Exception:  # noqa: BLE001 — langdetect raises on very short/ambiguous input
        lang = "de"

    hits = search_best(question, k)
    context = _build_context_block(hits)

    user_prompt = f"""\
Sprache der Frage: {lang}

FRAGE:
{question}

KONTEXT:
{context}
"""

    start = time.monotonic()
    llm = _get_llm_client()
    result, usage = llm.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        response_model=_RagLLMOutput,
    )
    response_time_s = time.monotonic() - start

    sources = [
        {"name": hit["name"], "legal_norm": hit["legal_norm"], "official_url": hit.get("official_url")}
        for hit in hits
    ]

    return RagAnswer(
        answer=result.answer,
        benefits_mentioned=result.benefits_mentioned,
        sources=sources,
        model=config.LLM_MODEL,
        prompt_variant=variant_key,
        response_time_s=response_time_s,
        prompt_tokens=usage["prompt_tokens"],
        completion_tokens=usage["completion_tokens"],
        cost_usd=usage["cost_usd"],
    )
