from __future__ import annotations

import argparse
import csv
import json
import logging
import statistics
import time
from pathlib import Path
from typing import Any

from src.config import load_config
from src.conversational_memory import ConversationMemory
from src.rag_pipeline import SYSTEM_PROMPT, chat


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPT_SET_PATH = PROJECT_ROOT / "eval" / "prompt_set.json"
DOCS_DIR = PROJECT_ROOT / "docs"
CSV_PATH = DOCS_DIR / "local-mode-comparison-results.csv"
MD_PATH = DOCS_DIR / "local-mode-comparison.md"


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0

    values = sorted(values)
    index = round((len(values) - 1) * p)

    return values[index]


def safe_markdown_cell(value: Any, max_chars: int = 220) -> str:
    text = str(value or "")
    text = text.replace("\n", " ")
    text = text.replace("|", "\\|")
    text = text.strip()

    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "..."

    return text


def load_prompt_set(path: Path = PROMPT_SET_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Prompt set not found: {path}")

    prompts = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(prompts, list):
        raise ValueError("prompt_set.json must contain a list of prompt objects.")

    required_keys = {"id", "category", "query"}

    for item in prompts:
        missing = required_keys - set(item.keys())

        if missing:
            raise ValueError(f"Prompt item missing keys {missing}: {item}")

    return prompts


def build_row(
    *,
    profile: str,
    item: dict[str, Any],
    result,
    error: str = "",
) -> dict[str, Any]:
    return {
        "profile": profile,
        "id": item.get("id", ""),
        "category": item.get("category", ""),
        "query": item.get("query", ""),
        "llm_profile": getattr(result, "llm_profile", profile) if result else profile,
        "llm_model": getattr(result, "llm_model", "") if result else "",
        "embedding_profile": getattr(result, "embedding_profile", profile) if result else profile,
        "embedding_model": getattr(result, "embedding_model", "") if result else "",
        "latency_sec": getattr(result, "latency_sec", 0.0) if result else 0.0,
        "tool_called": "yes" if result and getattr(result, "tool_names", []) else "no",
        "tool_names": ",".join(getattr(result, "tool_names", []) or []) if result else "",
        "retrieved_chunks": len(getattr(result, "chunks", []) or []) if result else 0,
        "answer": (getattr(result, "answer", "") or "").replace("\n", " ") if result else "",
        "error": error,
        "correctness_0_2": "",
        "citation_0_1": "",
        "refusal_0_1": "",
        "tool_correct_0_1": "",
        "notes": "",
    }


def run_profile(profile: str, prompts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Run the fixed prompt set against one profile.

    profile:
        local = Ollama LLM + Ollama embeddings
        azure = Azure LLM + Azure embeddings
    """
    cfg = load_config(
        llm_profile=profile,
        embedding_profile=profile,
    )

    print("=" * 80)
    print(f"RUNNING PROFILE: {profile.upper()}")
    print(f"LLM       : {cfg.llm_profile}:{cfg.resolved_llm_model}")
    print(f"Embedding : {cfg.embedding_profile}:{cfg.resolved_embedding_model}")
    print(f"Top-K     : {cfg.top_k}")
    print("=" * 80)

    rows: list[dict[str, Any]] = []

    for item in prompts:
        memory = ConversationMemory(SYSTEM_PROMPT)
        query = item["query"]

        try:
            result = chat(
                memory=memory,
                user_message=query,
                cfg=cfg,
            )

            row = build_row(
                profile=profile,
                item=item,
                result=result,
            )

            print(
                f"[{profile}] Q{item['id']} | "
                f"{result.latency_sec}s | "
                f"tools={result.tool_names or 'None'}"
            )

        except Exception as exc:
            logger.exception("Profile run failed | profile=%s | query_id=%s", profile, item.get("id"))

            row = build_row(
                profile=profile,
                item=item,
                result=None,
                error=str(exc),
            )

            print(f"[{profile}] Q{item['id']} failed: {exc}")

        rows.append(row)

    return rows


def aggregate_latency(rows: list[dict[str, Any]], profile: str) -> dict[str, float]:
    latencies = [
        float(row["latency_sec"])
        for row in rows
        if row["profile"] == profile and not row.get("error") and float(row["latency_sec"]) > 0
    ]

    if not latencies:
        return {
            "count": 0,
            "p50": 0.0,
            "p95": 0.0,
            "avg": 0.0,
            "min": 0.0,
            "max": 0.0,
        }

    return {
        "count": len(latencies),
        "p50": statistics.median(latencies),
        "p95": percentile(latencies, 0.95),
        "avg": statistics.mean(latencies),
        "min": min(latencies),
        "max": max(latencies),
    }


def write_csv(rows: list[dict[str, Any]], path: Path = CSV_PATH) -> None:
    path.parent.mkdir(exist_ok=True)

    if not rows:
        raise ValueError("No rows to write.")

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: list[dict[str, Any]], profiles: list[str], path: Path = MD_PATH) -> None:
    path.parent.mkdir(exist_ok=True)

    lines: list[str] = []

    lines.append("# Local Mode Comparison\n\n")

    lines.append("## Purpose\n\n")
    lines.append(
        "This report compares the same RAG application under different runtime profiles. "
        "The local profile uses Ollama for both LLM and embeddings. "
        "The Azure profile uses Azure OpenAI for both LLM and embeddings.\n\n"
    )

    lines.append("## Profiles Tested\n\n")
    lines.append("| Profile | LLM | Embedding | Notes |\n")
    lines.append("|---|---|---|---|\n")

    if "local" in profiles:
        lines.append("| Local | Ollama `gemma3n:e4b` | Ollama `nomic-embed-text` | Required local mode |\n")

    if "azure" in profiles:
        lines.append("| Azure | Azure `gpt-5.4-nano` | Azure `text-embedding-3-small` | Cloud baseline |\n")

    lines.append("\n## Aggregate Latency\n\n")
    lines.append("| Profile | Successful queries | p50 | p95 | Average | Min | Max |\n")
    lines.append("|---|---:|---:|---:|---:|---:|---:|\n")

    for profile in profiles:
        stats = aggregate_latency(rows, profile)
        lines.append(
            f"| {profile} | {int(stats['count'])} | "
            f"{stats['p50']:.3f}s | {stats['p95']:.3f}s | "
            f"{stats['avg']:.3f}s | {stats['min']:.3f}s | {stats['max']:.3f}s |\n"
        )

    lines.append("\n## Rubric\n\n")
    lines.append("- **Correctness 0-2:** 0 = wrong, 1 = partially correct, 2 = correct and grounded.\n")
    lines.append("- **Citation 0-1:** 0 = missing/weak, 1 = cites retrieved sources where needed.\n")
    lines.append("- **Refusal 0-1:** 0 = failed to refuse unsafe/unanswerable prompt, 1 = refused correctly.\n")
    lines.append("- **Tool Correct 0-1:** 0 = tool wrong/missed, 1 = tool used correctly where applicable.\n\n")

    lines.append("## Per-query Results\n\n")
    lines.append(
        "| Profile | ID | Category | Latency | Tool called | Chunks | Error | Manual scores/notes |\n"
    )
    lines.append("|---|---:|---|---:|---|---:|---|---|\n")

    for row in rows:
        lines.append(
            f"| {safe_markdown_cell(row['profile'])} "
            f"| {row['id']} "
            f"| {safe_markdown_cell(row['category'])} "
            f"| {row['latency_sec']} "
            f"| {safe_markdown_cell(row['tool_called'])} "
            f"| {row['retrieved_chunks']} "
            f"| {safe_markdown_cell(row['error'])} "
            f"| Fill manually |\n"
        )

    lines.append("\n## Prompt Set\n\n")

    seen_prompts = {}

    for row in rows:
        seen_prompts[row["id"]] = {
            "category": row["category"],
            "query": row["query"],
        }

    lines.append("| ID | Category | Query |\n")
    lines.append("|---:|---|---|\n")

    for prompt_id in sorted(seen_prompts, key=lambda x: int(x)):
        item = seen_prompts[prompt_id]
        lines.append(
            f"| {prompt_id} | {safe_markdown_cell(item['category'])} | {safe_markdown_cell(item['query'], 500)} |\n"
        )

    lines.append("\n## Diagnosis Notes To Fill\n\n")
    lines.append("### Retrieval quality\n")
    lines.append("- Check whether retrieved chunks are actually relevant.\n")
    lines.append("- Acronym and exact-term queries should benefit from hybrid retrieval.\n\n")

    lines.append("### Local model limitations\n")
    lines.append("- `gemma3n:e4b` may not support OpenAI-style tool calling in Ollama.\n")
    lines.append("- Local model may produce weaker strict JSON and complex multi-step reasoning.\n")
    lines.append("- Local latency depends strongly on RAM, CPU/GPU, and model quantization.\n\n")

    lines.append("### Azure strengths\n")
    lines.append("- Usually stronger tool calling, structured output, and complex reasoning.\n")
    lines.append("- Requires internet/API access and has per-request cost.\n\n")

    lines.append("### Recommendation summary\n")
    lines.append(
        "- Local mode is suitable for offline/private document retrieval where API cost and privacy are important.\n"
    )
    lines.append(
        "- Azure mode is suitable when tool reliability, speed consistency, and stronger reasoning are required.\n"
    )

    path.write_text("".join(lines), encoding="utf-8")


def run_comparison(profiles: list[str]) -> None:
    DOCS_DIR.mkdir(exist_ok=True)

    prompts = load_prompt_set(PROMPT_SET_PATH)

    all_rows: list[dict[str, Any]] = []

    start = time.perf_counter()

    for profile in profiles:
        try:
            all_rows.extend(run_profile(profile, prompts))
        except Exception as exc:
            print(f"Profile `{profile}` could not run: {exc}")

    if not all_rows:
        raise RuntimeError("No comparison results were generated.")

    write_csv(all_rows, CSV_PATH)
    write_markdown(all_rows, profiles, MD_PATH)

    elapsed = time.perf_counter() - start

    print("\n" + "=" * 80)
    print("COMPARISON COMPLETED")
    print("=" * 80)
    print(f"Profiles : {', '.join(profiles)}")
    print(f"Rows     : {len(all_rows)}")
    print(f"CSV      : {CSV_PATH}")
    print(f"Markdown : {MD_PATH}")
    print(f"Elapsed  : {elapsed:.2f} sec")
    print("=" * 80)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run local/cloud RAG comparison on fixed prompt set."
    )

    parser.add_argument(
        "--profiles",
        nargs="+",
        choices=["local", "azure"],
        default=["local", "azure"],
        help="Profiles to run. Example: --profiles local or --profiles local azure",
    )

    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    run_comparison(profiles=args.profiles)


if __name__ == "__main__":
    main()