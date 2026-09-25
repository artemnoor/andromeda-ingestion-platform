"""Closed, JSON-only validator for the Knowledge Core Rule DSL."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

ALLOWED_KINDS = {
    "literal",
    "logical",
    "comparison",
    "exists",
    "not_exists",
    "membership",
    "aggregation",
    "quantifier",
    "fact",
    "facts",
    "relation",
    "relations",
    "context",
    "applicant",
    "collection",
}
LOGICAL = {"and", "or", "not"}
COMPARISON = {"==", "!=", ">", ">=", "<", "<="}
MEMBERSHIP = {"in", "not_in"}
AGGREGATION = {"count", "sum", "min", "max"}
QUANTIFIERS = {"any", "all", "none", "at_least"}
EFFECTS = {"SET", "ADD", "SUBTRACT", "GRANT", "DENY", "MARK_ELIGIBLE", "MARK_INELIGIBLE", "EMIT_DERIVED"}


def validate_rule_dsl(node: Any, max_depth: int = 30) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    _validate(node, "$", 0, max_depth, errors)
    return errors


def validate_rule_effects(effects: Any) -> list[dict[str, str]]:
    """Validate effect shape required by the Knowledge Core rule contract."""
    if not isinstance(effects, list) or not effects:
        return [{"path": "effects", "message": "At least one declarative effect is required."}]
    errors: list[dict[str, str]] = []
    for index, effect in enumerate(effects):
        path = f"effects[{index}]"
        if not isinstance(effect, Mapping):
            errors.append({"path": path, "message": "Effect must be an object."})
            continue
        effect_type = effect.get("type")
        if effect_type not in EFFECTS:
            errors.append({"path": f"{path}.type", "message": f"Unknown effect '{effect_type}'."})
        if not isinstance(effect.get("target"), str) or not effect["target"]:
            errors.append({"path": f"{path}.target", "message": "Effect target is required."})
        if effect_type not in {"MARK_ELIGIBLE", "MARK_INELIGIBLE"} and "value" not in effect:
            errors.append({"path": f"{path}.value", "message": "This effect requires a value."})
        value = effect.get("value")
        if isinstance(value, dict) and "kind" in value:
            errors.extend({**error, "path": f"{path}.{error['path']}"} for error in validate_rule_dsl(value))
    return errors


def _validate(node: Any, path: str, depth: int, max_depth: int, errors: list[dict[str, str]]) -> None:
    if depth > max_depth:
        errors.append({"path": path, "message": f"DSL nesting exceeds {max_depth} levels"})
        return
    if isinstance(node, (str, int, float, bool)) or node is None:
        return
    if isinstance(node, list):
        for index, child in enumerate(node):
            _validate(child, f"{path}[{index}]", depth + 1, max_depth, errors)
        return
    if not isinstance(node, Mapping):
        errors.append({"path": path, "message": "DSL node must be JSON object, array or literal"})
        return
    kind = node.get("kind", node.get("op"))
    if kind not in ALLOWED_KINDS:
        errors.append({"path": f"{path}.kind", "message": f"Unknown DSL node kind '{kind}'"})
        return
    if kind == "literal":
        if "value" not in node:
            errors.append({"path": path, "message": "literal requires value"})
        return
    if kind == "logical":
        operator = node.get("operator")
        args = node.get("args")
        if operator not in LOGICAL or not isinstance(args, list) or not args or (operator == "not" and len(args) != 1):
            errors.append({"path": path, "message": "invalid logical operator or arity"})
        for index, child in enumerate(args or []):
            _validate(child, f"{path}.args[{index}]", depth + 1, max_depth, errors)
        return
    if kind in {"comparison", "membership"}:
        operators = COMPARISON if kind == "comparison" else MEMBERSHIP
        if node.get("operator") not in operators:
            errors.append({"path": f"{path}.operator", "message": "unknown operator"})
        for field in ("left", "right"):
            if field not in node:
                errors.append({"path": f"{path}.{field}", "message": "missing operand"})
            else:
                _validate(node[field], f"{path}.{field}", depth + 1, max_depth, errors)
        return
    if kind in {"exists", "not_exists", "aggregation"}:
        if "target" not in node:
            errors.append({"path": f"{path}.target", "message": "missing target"})
        else:
            _validate(node["target"], f"{path}.target", depth + 1, max_depth, errors)
        if kind == "aggregation" and node.get("operator") not in AGGREGATION:
            errors.append({"path": f"{path}.operator", "message": "unknown aggregation operator"})
        return
    if kind == "quantifier":
        if node.get("operator") not in QUANTIFIERS or not isinstance(node.get("items"), list) or not node["items"]:
            errors.append({"path": path, "message": "invalid quantifier"})
        if node.get("operator") == "at_least" and (not isinstance(node.get("count"), int) or node["count"] < 0):
            errors.append({"path": f"{path}.count", "message": "at_least requires non-negative integer count"})
        for index, child in enumerate(node.get("items", [])):
            _validate(child, f"{path}.items[{index}]", depth + 1, max_depth, errors)
        return
    if kind in {"fact", "facts", "collection"} and not isinstance(node.get("property"), str):
        errors.append({"path": f"{path}.property", "message": "reference requires property"})
    if kind in {"relation", "relations"} and not isinstance(node.get("relation_type"), str):
        errors.append({"path": f"{path}.relation_type", "message": "relation reference requires relation_type"})
    if kind in {"context", "applicant"} and not isinstance(node.get("path"), str):
        errors.append({"path": f"{path}.path", "message": "context reference requires path"})
