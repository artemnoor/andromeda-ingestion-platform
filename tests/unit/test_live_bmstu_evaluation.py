from copy import deepcopy

from scripts.live_bmstu_e2e import (
    _condition_matches_expectation,
    _fact_expectation_metrics,
    _golden_metrics,
    _organization_for_entry,
    _rule_condition_metrics,
    _rule_effect_matches_expectation,
)


def test_golden_metrics_ignore_values_present_only_in_evidence_quotes() -> None:
    extraction = {
        "result_json": {
            "facts": [
                {
                    "candidate_id": "fact-placeholder",
                    "property_code": "admission.minimum_score",
                    "value": 46,
                    "metadata": {"section": "Other", "exam_subject": "Other"},
                    "evidence": [{"quote": "GUIMC Russian language minimum is 46"}],
                }
            ]
        }
    }
    entry = {
        "golden_expectations": [
            {"field": "GUIMC Russian-language minimum", "value": "46", "kind": "number"}
        ]
    }

    result = _golden_metrics(entry, extraction)

    assert result["field_accuracy"] == 0


def test_source_organization_uses_the_official_publisher_host() -> None:
    assert _organization_for_entry({"url": "https://kf.bmstu.ru/edu/kf/iuk/iuk5"}) == "Калужский филиал МГТУ им. Н.Э. Баумана"
    assert _organization_for_entry({"url": "https://api.www.bmstu.ru/file/123748/download"}) == "МГТУ им. Н.Э. Баумана"


def test_rule_condition_golden_preserves_and_or_grouping_and_thresholds() -> None:
    def comparison(subject: str) -> dict:
        return {
            "kind": "comparison",
            "operator": ">=",
            "left": {"kind": "fact", "subject": "applicant", "property": "exam_score", "exam_subject": subject},
            "right": {"kind": "literal", "value": 46},
        }

    rule = {
        "scope": {"section": "GUIMC"},
        "conditions": {
            "kind": "logical",
            "operator": "and",
            "args": [
                comparison("Русский язык"),
                comparison("Математика"),
                {"kind": "logical", "operator": "or", "args": [comparison("Физика"), comparison("Информатика и ИКТ")]},
            ],
        },
    }
    expectation = {
        "section": "GUIMC",
        "all_conditions": [
            {"subject": "Русский язык", "operator": ">=", "threshold": 46},
            {"subject": "Математика", "operator": ">=", "threshold": 46},
        ],
        "any_conditions": [
            {"subject": "Физика", "operator": ">=", "threshold": 46},
            {"subject": "Информатика и ИКТ", "operator": ">=", "threshold": 46},
        ],
    }

    assert _condition_matches_expectation(rule, expectation)
    assert _rule_condition_metrics({"rule_condition_expectations": [expectation]}, [rule])["accuracy"] == 1
    wrong_and = {
        **rule,
        "conditions": {"kind": "logical", "operator": "and", "args": [*rule["conditions"]["args"][:2], comparison("Физика"), comparison("Информатика и ИКТ")]},
    }
    assert not _condition_matches_expectation(wrong_and, expectation)


def test_rule_effect_golden_requires_a_non_admission_effect() -> None:
    expectation = {"type": "EMIT_DERIVED", "target": "entrance_exams_passed", "value": True}

    assert _rule_effect_matches_expectation({"effects": [expectation]}, expectation)
    assert not _rule_effect_matches_expectation(
        {"effects": [{"type": "EMIT_DERIVED", "value": "listed_exams_passed"}]}, expectation
    )


def test_mytishchi_golden_requires_one_structured_fact_with_exact_markers() -> None:
    expected = {
        "section": "Mytishchi branch",
        "property_code": "admission.minimum_scores_by_exam",
        "program_code": "09.03.01",
        "minimums": [
            {"subject": "Русский язык", "minimum": 40, "printed_marker": "III"},
            {"subject": "Математика", "minimum": 40, "printed_marker": "II"},
            {"subject": "Физика", "minimum": 41, "printed_marker": "I"},
            {"subject": "Информатика и ИКТ", "minimum": 46, "printed_marker": "I"},
        ],
    }
    extraction = {
        "facts": [
            {
                "property_code": expected["property_code"],
                "value": {"section": "Mytishchi branch", "program_code": "09.03.01", "minimums": expected["minimums"]},
                "metadata": {"section": "Mytishchi branch", "program_code": "09.03.01"},
            }
        ]
    }

    result = _fact_expectation_metrics({"fact_expectations": [expected]}, extraction)

    assert result["accuracy"] == 1
    changed = deepcopy(extraction)
    changed["facts"][0]["value"]["minimums"][2]["minimum"] = 46
    assert _fact_expectation_metrics({"fact_expectations": [expected]}, changed)["accuracy"] == 0
