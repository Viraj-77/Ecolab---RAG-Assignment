"""Observability module — JSON-line logger + timeline query helper.

The contract: any code that emits an A2A event calls ``log_event`` with the
same set of structured fields. The sink is a single ndjson file
(``observability/logs.ndjson``) that ``query.py`` can re-sort by timestamp
to answer the rubric's "why did agent X call agent Y?" question without
re-running the workflow.
"""
from .logger import LOG_PATH, configure_root, log_event

__all__ = ["LOG_PATH", "configure_root", "log_event"]
