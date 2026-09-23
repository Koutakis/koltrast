import argparse
import json
import re
from pathlib import Path
from collections import Counter


PLACEHOLDER = "[NAME]"
PLACEHOLDER_PATTERN = re.compile(r"\[(?:name|namn)\]", re.IGNORECASE)


def load_tests(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_jsonl(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def norm(value: str):
    return value.strip(" \t\n\r.,;:!?\"'“”()[]{}").casefold()


def expected_variants(name: str):
    base = norm(name)
    return {base, base + "s"}


def extract_replaced_text(original: str, anonymized: str):
    if not PLACEHOLDER_PATTERN.search(anonymized):
        return []

    parts = PLACEHOLDER_PATTERN.split(anonymized)

    pattern = "^"
    for i, part in enumerate(parts):
        pattern += re.escape(part)
        if i < len(parts) - 1:
            pattern += "(.+?)"
    pattern += "$"

    match = re.match(pattern, original)
    if not match:
        return [PLACEHOLDER]

    return [group.strip() for group in match.groups() if group.strip()]


def extract_jsonl_predictions(row):
    predictions = []

    for result in row.get("results", []):
        if isinstance(result, str):
            predictions.append(result)
        elif isinstance(result, dict):
            if "text" in result:
                predictions.append(result["text"])
            elif "start" in result and "end" in result:
                text = row["text"]
                predictions.append(text[result["start"]:result["end"]])

    return [p for p in predictions if p.strip()]


def compare_rows(rows):
    stats = Counter()
    fp_examples = []
    fn_examples = []

    for idx, row in enumerate(rows):
        original = row["text"]
        expected = row.get("expected", [])
        predictions = row.get("predictions", [])

        if expected and all(norm(item) == "name" for item in expected):
            stats["rows"] += 1
            stats["expected_entities"] += len(expected)
            stats["predicted_entities"] += len(predictions)

            true_positive_count = min(len(expected), len(predictions))
            stats["true_positives"] += true_positive_count

            for pred in predictions[true_positive_count:]:
                stats["false_positives"] += 1
                fp_examples.append({
                    "row": idx + 1,
                    "text": original,
                    "false_positive": pred,
                    "expected": expected,
                })

            for _ in expected[true_positive_count:]:
                stats["false_negatives"] += 1
                fn_examples.append({
                    "row": idx + 1,
                    "text": original,
                    "missing_expected": "NAME",
                    "predictions": predictions,
                })

            continue

        expected_norm = set()
        for name in expected:
            expected_norm.update(expected_variants(name))

        matched_expected = set()

        stats["rows"] += 1
        stats["expected_entities"] += len(expected)
        stats["predicted_entities"] += len(predictions)

        for pred in predictions:
            pred_norm = norm(pred)

            if pred_norm in expected_norm:
                stats["true_positives"] += 1
                matched_expected.add(pred_norm)
            else:
                stats["false_positives"] += 1
                fp_examples.append({
                    "row": idx + 1,
                    "text": original,
                    "false_positive": pred,
                    "expected": expected,
                })

        for exp in expected:
            if not expected_variants(exp).intersection(matched_expected):
                stats["false_negatives"] += 1
                fn_examples.append({
                    "row": idx + 1,
                    "text": original,
                    "missing_expected": exp,
                    "predictions": predictions,
                })

    return stats, fp_examples, fn_examples


def compare_jsonl_results(test_file: Path, result_file: Path):
    tests = load_tests(test_file)
    result_rows = load_jsonl(result_file)

    rows = []
    for idx, result_row in enumerate(result_rows):
        expected = result_row.get("expected")

        if expected is None and idx < len(tests):
            expected = tests[idx].get("expected", [])

        rows.append({
            "text": result_row["text"],
            "expected": expected or [],
            "predictions": extract_jsonl_predictions(result_row),
        })

    stats, fp_examples, fn_examples = compare_rows(rows)
    stats["test_rows"] = len(tests)
    stats["result_rows"] = len(result_rows)
    stats["missing_result_rows"] = max(0, len(tests) - len(result_rows))
    stats["extra_result_rows"] = max(0, len(result_rows) - len(tests))

    return stats, fp_examples, fn_examples


def compare_txt_results(test_file: Path, result_file: Path):
    tests = load_tests(test_file)
    result_lines = result_file.read_text(encoding="utf-8").splitlines()

    rows = []
    row_count = min(len(tests), len(result_lines))

    for idx in range(row_count):
        original = tests[idx]["text"]
        anonymized = result_lines[idx].strip()

        rows.append({
            "text": original,
            "expected": tests[idx].get("expected", []),
            "predictions": extract_replaced_text(original, anonymized),
        })

    stats, fp_examples, fn_examples = compare_rows(rows)
    stats["test_rows"] = len(tests)
    stats["result_rows"] = len(result_lines)
    stats["missing_result_rows"] = max(0, len(tests) - len(result_lines))
    stats["extra_result_rows"] = max(0, len(result_lines) - len(tests))

    return stats, fp_examples, fn_examples


def compare_results(test_file: Path, result_file: Path):
    if result_file.suffix.lower() == ".jsonl":
        return compare_jsonl_results(test_file, result_file)

    return compare_txt_results(test_file, result_file)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("result_files", nargs="+")
    parser.add_argument("--tests", default="test_strings.jsonl")
    parser.add_argument("--show", type=int, default=30)
    args = parser.parse_args()

    test_file = Path(args.tests)

    for result_path in args.result_files:
        result_file = Path(result_path)

        if not result_file.is_file():
            print(f"\nSkipping non-file: {result_file}")
            continue

        stats, fp_examples, fn_examples = compare_results(test_file, result_file)

        precision = (
            stats["true_positives"] / stats["predicted_entities"]
            if stats["predicted_entities"]
            else 0
        )
        recall = (
            stats["true_positives"] / stats["expected_entities"]
            if stats["expected_entities"]
            else 0
        )
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0
        )

        print(f"\n=== {result_file} ===")
        print(f"Test rows:            {stats['test_rows']}")
        print(f"Result rows:          {stats['result_rows']}")
        print(f"Rows compared:        {stats['rows']}")
        print(f"Expected entities:    {stats['expected_entities']}")
        print(f"Predicted entities:   {stats['predicted_entities']}")
        print(f"True positives:       {stats['true_positives']}")
        print(f"False positives:      {stats['false_positives']}")
        print(f"False negatives:      {stats['false_negatives']}")
        print(f"Precision:            {precision:.3f}")
        print(f"Recall:               {recall:.3f}")
        print(f"F1 score:             {f1:.3f}")

        if stats["missing_result_rows"]:
            print(f"Missing result rows:  {stats['missing_result_rows']}")

        if stats["extra_result_rows"]:
            print(f"Extra result rows:    {stats['extra_result_rows']}")

        if fp_examples:
            print("\nFalse-positive examples:")
            for example in fp_examples[:args.show]:
                print(json.dumps(example, ensure_ascii=False))

        if fn_examples:
            print("\nFalse-negative examples:")
            for example in fn_examples[:args.show]:
                print(json.dumps(example, ensure_ascii=False))


if __name__ == "__main__":
    main()