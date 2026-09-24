from scripts.evaluate_golden import evaluate


def test_golden_extraction_metrics_are_complete():
    import asyncio

    metrics = asyncio.run(evaluate())
    assert metrics
    for item in metrics:
        assert item["rule_accuracy"] == 1.0
        assert item["threshold_accuracy"] == 1.0
        assert item["evidence_locator_accuracy"] == 1.0
        assert item["unknown_concept_accuracy"] == 1.0
