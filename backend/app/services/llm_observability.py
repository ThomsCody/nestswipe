"""Keep optional tracing annotations from interrupting application work."""

import logging

from ddtrace.llmobs import LLMObs

logger = logging.getLogger(__name__)


def annotate_llm(*, metadata: dict, metrics: dict) -> None:
    if not LLMObs.enabled:
        return
    try:
        LLMObs.annotate(metadata=metadata, metrics=metrics)
    except Exception:
        logger.warning("Unable to annotate LLM observability span", exc_info=True)
