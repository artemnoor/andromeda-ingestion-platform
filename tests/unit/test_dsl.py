from andromeda_ingestion.domain.validation.dsl import validate_rule_dsl


def test_valid_at_least_rule() -> None:
    node = {
        "kind": "quantifier",
        "operator": "at_least",
        "count": 2,
        "items": [
            {"kind": "context", "path": "a"},
            {"kind": "context", "path": "b"},
            {"kind": "context", "path": "c"},
        ],
    }
    assert validate_rule_dsl(node) == []


def test_unknown_operator_is_rejected_without_execution() -> None:
    node = {"kind": "comparison", "operator": "eval", "left": {"kind": "literal", "value": 1}, "right": {"kind": "literal", "value": 1}}
    errors = validate_rule_dsl(node)
    assert errors
    assert "unknown operator" in errors[0]["message"]
