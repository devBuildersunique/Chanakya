"""Score isolated UIE output against synthetic, mention-level directed edges.

Run with .uie-test/Scripts/python.exe; --validate-only needs only standard Python.
Model probabilities are intentionally not used as calibrated edge confidence.
"""

import argparse
import json
import re
import statistics
import sys
from pathlib import Path
from time import perf_counter

from relationship_cases import CASES, PREDICATES, SCHEMA


UIE_ENV = Path(__file__).resolve().parents[1] / ".uie-test"


def mention_span(text, mention):
    surface, separator, occurrence_text = mention.rpartition("#")
    if not separator or not surface or not occurrence_text.isdecimal():
        raise ValueError(f"Invalid mention selector: {mention!r}")
    matches = list(re.finditer(re.escape(surface), text))
    occurrence = int(occurrence_text)
    if occurrence >= len(matches):
        raise ValueError(f"Mention {mention!r} not found in {text!r}")
    return matches[occurrence].span()


def gold_edges(text, expected):
    return {
        (relation, *mention_span(text, head), *mention_span(text, tail))
        for relation, head, tail in expected
    }


def validate_fixture():
    if not 20 <= len(CASES) <= 30:
        raise ValueError("Fixture must contain 20–30 cases")
    ids = [case_id for case_id, _, _ in CASES]
    if len(ids) != len(set(ids)):
        raise ValueError("Fixture case IDs must be unique")
    for case_id, text, expected in CASES:
        for relation, _, _ in expected:
            if relation not in PREDICATES.values():
                raise ValueError(f"Case {case_id}: unknown gold predicate {relation!r}")
        if len(expected) != len(gold_edges(text, expected)):
            raise ValueError(f"Case {case_id}: duplicate gold edge")


def _span(text, item):
    start, end = item.get("start"), item.get("end")
    surface = item.get("text")
    valid = (
        type(start) is int
        and type(end) is int
        and isinstance(surface, str)
        and 0 <= start < end <= len(text)
        and text[start:end] == surface
    )
    return ((start, end) if valid else None), valid


def predicted_edges(text, result):
    if not isinstance(result, list) or any(not isinstance(row, dict) for row in result):
        raise ValueError(f"Unexpected UIE result shape: {type(result).__name__}")
    valid_edges = set()
    span_correct = span_total = bad_spans = 0
    for row in result:
        subjects = row.get("Person", [])
        if not isinstance(subjects, list):
            raise ValueError("UIE 'Person' result must be a list")
        for subject in subjects:
            if not isinstance(subject, dict):
                raise ValueError("UIE subject must be a mapping")
            relations = subject.get("relations", {})
            if not isinstance(relations, dict):
                raise ValueError("UIE relations must be a mapping")
            head_span, head_ok = _span(text, subject)
            for label, objects in relations.items():
                if not isinstance(objects, list):
                    raise ValueError(f"UIE relation {label!r} must contain a list")
                for obj in objects:
                    if not isinstance(obj, dict):
                        raise ValueError("UIE relation object must be a mapping")
                    tail_span, tail_ok = _span(text, obj)
                    span_total += 1
                    if head_ok and tail_ok:
                        span_correct += 1
                        valid_edges.add((PREDICATES.get(label, label), *head_span, *tail_span))
                    else:
                        bad_spans += 1
    return valid_edges, span_correct, span_total, bad_spans


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true", help="check gold data without loading UIE")
    args = parser.parse_args()
    validate_fixture()
    if args.validate_only:
        print(f"Validated {len(CASES)} synthetic cases; no inference run.")
        return

    if sys.version_info[:2] != (3, 11) or Path(sys.prefix).resolve() != UIE_ENV.resolve():
        parser.error("Run inference with this repository's .uie-test Python 3.11 environment")

    from paddlenlp import Taskflow

    model = Taskflow("information_extraction", model="uie-base-en", schema=SCHEMA, device_id=-1)
    totals = {"correct_edges": 0, "false_positive_edges": 0, "missed_relations": 0,
              "correct_abstentions": 0, "exact_cases": 0, "correct_spans": 0,
              "predicted_spans": 0, "invalid_span_edges": 0}
    case_results = []
    for case_id, text, expected in CASES:
        gold = gold_edges(text, expected)
        start = perf_counter()
        result = model(text)
        elapsed = perf_counter() - start
        predicted, span_correct, span_total, bad_spans = predicted_edges(text, result)
        tp = len(predicted & gold)
        fp = len(predicted - gold) + bad_spans
        fn = len(gold - predicted)
        abstained = not gold and not predicted and bad_spans == 0
        totals["correct_edges"] += tp
        totals["false_positive_edges"] += fp
        totals["missed_relations"] += fn
        totals["correct_abstentions"] += int(abstained)
        totals["exact_cases"] += int(fp == 0 and fn == 0)
        totals["correct_spans"] += span_correct
        totals["predicted_spans"] += span_total
        totals["invalid_span_edges"] += bad_spans
        case_results.append({"id": case_id, "tp": tp, "fp": fp, "fn": fn,
                             "correct_abstention": abstained, "seconds": round(elapsed, 4)})

    times = [case["seconds"] for case in case_results]
    summary = {"cases": len(CASES), "no_relation_cases": sum(not gold for _, _, gold in CASES),
               **totals, "inference_seconds_total": round(sum(times), 4),
               "inference_seconds_mean": round(statistics.mean(times), 4),
               "inference_seconds_max": round(max(times), 4), "per_case": case_results}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
