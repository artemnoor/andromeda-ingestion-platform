import json
import logging

from andromeda_ingestion.infrastructure.observability.logging import JsonFormatter


def test_json_formatter_includes_safe_metrics_and_redacts_secrets() -> None:
    record = logging.LogRecord(
        name="andromeda_ingestion.ai",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="ai_extraction_completed",
        args=(),
        exc_info=None,
    )
    record.request_bytes = 1024
    record.document_chunk_count = 3
    record.token_usage = {"prompt_tokens": 15, "completion_tokens": 7, "total_tokens": 22}
    record.api_key = "must-not-appear"
    record.secret_value = "must-not-appear-either"

    encoded = JsonFormatter().format(record)
    payload = json.loads(encoded)

    assert payload["request_bytes"] == 1024
    assert payload["document_chunk_count"] == 3
    assert payload["token_usage"] == {"prompt_tokens": 15, "completion_tokens": 7, "total_tokens": 22}
    assert payload["api_key"] == "[REDACTED]"
    assert payload["secret_value"] == "[REDACTED]"
    assert "must-not-appear" not in encoded
