"""Prometheus-compatible metrics adapter."""

from __future__ import annotations

from prometheus_client import Counter, Histogram, generate_latest

from andromeda_ingestion.domain.ports.observability import MetricsPort

_COUNTERS: dict[str, Counter] = {}
_HISTOGRAMS: dict[str, Histogram] = {}


def _counter(name: str, labels: tuple[str, ...]) -> Counter:
    metric = _COUNTERS.get(name)
    if metric is None:
        metric = Counter(name, name.replace("_", " "), labels)
        _COUNTERS[name] = metric
    return metric


def _histogram(name: str, labels: tuple[str, ...]) -> Histogram:
    metric = _HISTOGRAMS.get(name)
    if metric is None:
        metric = Histogram(name, name.replace("_", " "), labels)
        _HISTOGRAMS[name] = metric
    return metric


class PrometheusMetrics(MetricsPort):
    def increment(self, name: str, labels: dict[str, str] | None = None, value: float = 1) -> None:
        labels = labels or {}
        keys = tuple(sorted(labels))
        metric = _counter(name, keys)
        metric.labels(**{key: labels[key] for key in keys}).inc(value) if keys else metric.inc(value)

    def observe(self, name: str, duration_seconds: float, labels: dict[str, str] | None = None) -> None:
        labels = labels or {}
        keys = tuple(sorted(labels))
        metric = _histogram(name, keys)
        metric.labels(**{key: labels[key] for key in keys}).observe(duration_seconds) if keys else metric.observe(duration_seconds)


metrics = PrometheusMetrics()


def metrics_payload() -> bytes:
    return generate_latest()
