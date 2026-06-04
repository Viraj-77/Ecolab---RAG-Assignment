"""Intent classifier — keyword first-pass, LLM fallback hook (best-effort).

The orchestrator must answer one question per user request: which capability
should this go to? For Tech Radar Concierge that's a 2-way pick:
    answer-from-corpus     — explanatory ("why is X in HOLD?", "what is...")
    propose-radar-change   — mutation ("add X", "move Y to ADOPT", "remove Z")

We use a deterministic keyword classifier first because it's cheap, traceable,
and explainable. If the keyword pass returns ``ambiguous`` we *would* call a
small LLM. To keep the bootcamp environment runnable on a fresh laptop without
Azure credentials, the LLM hook is best-effort: if no client is configured it
falls back to the more conservative read-only capability and logs the reason.

Either way the classifier ALWAYS returns a ``ClassifierDecision`` with the full
prompt text, the matched keywords (for keyword path) or the model
prompt+response (for LLM path), and the chosen capability. The orchestrator
logs the whole decision struct as an ``intent_classified`` event so the
"why did X call Y" question is answerable from the log alone.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

WRITE_KEYWORDS = (
    "add",
    "propose",
    "change",
    "remove",
    "delete",
    "move",
    "promote",
    "demote",
    "assign",
    "unassign",
    "create",
)
READ_KEYWORDS = (
    "explain",
    "what is",
    "what's",
    "why",
    "how",
    "describe",
    "tell me",
    "history",
    "list",
    "show",
    "current",
)

CAP_RAG = "answer-from-corpus"
CAP_MCP = "propose-radar-change"


@dataclass
class ClassifierDecision:
    """Everything we want logged about a single classification pass."""

    user_request: str
    chosen_capability: str
    method: str  # "keyword" | "llm" | "fallback"
    matched_keywords: list[str] = field(default_factory=list)
    llm_prompt: Optional[str] = None
    llm_response: Optional[str] = None
    reasoning: Optional[str] = None

    def to_log_extras(self) -> dict:
        return {
            "user_request": self.user_request,
            "chosen_capability": self.chosen_capability,
            "method": self.method,
            "matched_keywords": self.matched_keywords,
            "llm_prompt": self.llm_prompt,
            "llm_response": self.llm_response,
            "classifier_reasoning": self.reasoning,
        }


def _keyword_pass(text: str) -> tuple[Optional[str], list[str]]:
    """Return (capability, matched_keywords) — capability is None when ambiguous."""
    lc = text.lower()
    write_hits = [kw for kw in WRITE_KEYWORDS if kw in lc]
    read_hits = [kw for kw in READ_KEYWORDS if kw in lc]
    if write_hits and not read_hits:
        return CAP_MCP, write_hits
    if read_hits and not write_hits:
        return CAP_RAG, read_hits
    if write_hits and read_hits:
        # Both present: write keywords win, because the user clearly wants
        # something done; we'll have logged the conflict for the human reader.
        return CAP_MCP, write_hits + read_hits
    return None, []


_LLM_PROMPT_TEMPLATE = """You are an intent router for the Ecolab Tech Radar.

Available capabilities:
  - {cap_rag}: ask questions about the radar, its history, or rationale.
  - {cap_mcp}: propose a structured change (add, assign, move, remove).

Reply with EXACTLY one capability string and nothing else.

User request: {user_request}
""".strip()


def _try_llm(prompt: str) -> Optional[str]:
    """Best-effort call to Azure OpenAI. Returns the raw text reply or None.

    Reuses the same Azure config the vendored exercise-a-rag pipeline uses.
    Skipped silently when ``AZURE_OPENAI_API_KEY`` is not set so the
    orchestrator stays runnable on a fresh laptop.
    """
    if not os.environ.get("AZURE_OPENAI_API_KEY"):
        return None
    try:  # pragma: no cover — environmental
        from openai import AzureOpenAI  # type: ignore

        client = AzureOpenAI(
            api_version="2024-12-01-preview",
            azure_endpoint="https://cds-ds-openai-001-x.openai.azure.com/",
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
        )
        resp = client.chat.completions.create(
            model="gpt-5.4-nano",
            messages=[{"role": "user", "content": prompt}],
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return None


def classify(user_request: str) -> ClassifierDecision:
    """Classify a user request into a capability. Always returns a decision."""
    text = (user_request or "").strip()
    if not text:
        return ClassifierDecision(
            user_request=user_request,
            chosen_capability=CAP_RAG,
            method="fallback",
            reasoning="empty request — defaulting to read-only capability",
        )

    cap, matches = _keyword_pass(text)
    if cap is not None:
        return ClassifierDecision(
            user_request=text,
            chosen_capability=cap,
            method="keyword",
            matched_keywords=matches,
            reasoning="keyword-only path; no LLM call needed",
        )

    # Ambiguous — try the LLM hook.
    prompt = _LLM_PROMPT_TEMPLATE.format(
        cap_rag=CAP_RAG, cap_mcp=CAP_MCP, user_request=text
    )
    llm_reply = _try_llm(prompt)
    if llm_reply:
        chosen = CAP_MCP if CAP_MCP in llm_reply else CAP_RAG
        return ClassifierDecision(
            user_request=text,
            chosen_capability=chosen,
            method="llm",
            llm_prompt=prompt,
            llm_response=llm_reply,
            reasoning="ambiguous keywords; LLM disambiguated",
        )

    # No keywords AND no LLM available — fall back to read-only,
    # which is the lower-blast-radius default.
    return ClassifierDecision(
        user_request=text,
        chosen_capability=CAP_RAG,
        method="fallback",
        llm_prompt=prompt,
        reasoning="ambiguous keywords and no LLM configured; defaulted to read-only",
    )


__all__ = ["classify", "ClassifierDecision", "CAP_RAG", "CAP_MCP"]
