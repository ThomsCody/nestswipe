"""Regression coverage for CVE-2026-50271 without sending HTTP requests."""

import pytest
from ddtrace import config
from ddtrace.propagation.http import HTTPPropagator

TRACE_ID = "1234567890abcdef1234567890abcdef"
PARENT_ID = "1234567890abcdef"


@pytest.fixture(autouse=True)
def extraction_styles(monkeypatch):
    monkeypatch.setattr(
        config, "_propagation_style_extract", ["datadog", "tracecontext", "baggage"]
    )


def extract(baggage):
    context = HTTPPropagator.extract(
        {
            "traceparent": f"00-{TRACE_ID}-{PARENT_ID}-01",
            "baggage": baggage,
        }
    )
    # Baggage limits must not break distributed trace correlation.
    assert context.trace_id == int(TRACE_ID, 16)
    assert context.span_id == int(PARENT_ID, 16)
    return context.get_all_baggage_items()


def test_baggage_accepts_normal_values():
    assert extract("source=nestswipe,label=Paris%20centre") == {
        "source": "nestswipe",
        "label": "Paris centre",
    }


def test_baggage_caps_incoming_item_count():
    baggage = extract(",".join(f"item{i}=value" for i in range(100)))
    assert len(baggage) <= 64
    assert baggage["item0"] == "value"
    assert "item99" not in baggage


@pytest.mark.parametrize("value", ["x" * 8192, "é" * 4096])
def test_baggage_rejects_oversized_value(value):
    assert extract(f"oversized={value}") == {}


def test_baggage_caps_total_bytes():
    baggage = extract(",".join(f"item{i}={'x' * 1024}" for i in range(10)))
    assert baggage["item0"] == "x" * 1024
    assert "item9" not in baggage
    assert (
        len(",".join(f"{key}={value}" for key, value in baggage.items()).encode())
        <= 8192
    )
