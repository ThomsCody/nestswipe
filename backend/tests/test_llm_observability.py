from unittest.mock import Mock

from app.services.llm_observability import LLMObs, annotate_llm


def test_annotations_are_skipped_when_llm_observability_is_disabled(monkeypatch):
    monkeypatch.setattr(LLMObs, "enabled", False)
    annotate = Mock()
    monkeypatch.setattr(LLMObs, "annotate", annotate)
    annotate_llm(metadata={"model": "gpt-4o-mini"}, metrics={"input_tokens": 12})
    annotate.assert_not_called()


def test_annotations_are_forwarded_when_enabled(monkeypatch):
    monkeypatch.setattr(LLMObs, "enabled", True)
    annotate = Mock()
    monkeypatch.setattr(LLMObs, "annotate", annotate)
    annotate_llm(metadata={"model": "gpt-4o-mini"}, metrics={"input_tokens": 12})
    annotate.assert_called_once_with(
        metadata={"model": "gpt-4o-mini"}, metrics={"input_tokens": 12}
    )


def test_annotation_errors_do_not_interrupt_application_work(monkeypatch, caplog):
    monkeypatch.setattr(LLMObs, "enabled", True)
    monkeypatch.setattr(
        LLMObs, "annotate", Mock(side_effect=ValueError("No active span"))
    )
    annotate_llm(metadata={}, metrics={})
    assert "Unable to annotate LLM observability span" in caplog.text
