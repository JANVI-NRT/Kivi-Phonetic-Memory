import json
import time
import argparse
from pathlib import Path

from app.database import SessionLocal
from app.models import Memory, Observation
from app.services.formatting_service import format_with_memory
from app.services.memory_service import learn_memory


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CASES_FILE = BASE_DIR / "cases.json"
DEFAULT_RESULTS_FILE = BASE_DIR / "results.json"


def reset_database(db) -> None:
    db.query(Observation).delete()
    db.query(Memory).delete()
    db.commit()


def seed_memories(db, case: dict) -> None:
    memories = case.get("memories")

    if memories is None:
        memories = [case["memory"]]

    for memory in memories:
        learn_memory(
            db=db,
            spoken_form=memory["spoken_form"],
            preferred_form=memory["preferred_form"],
            context=memory.get("context"),
            language=memory.get("language"),
        )


def run_case(case: dict) -> dict:
    db = SessionLocal()

    try:
        reset_database(db)
        seed_memories(db, case)

        start = time.perf_counter()

        result = format_with_memory(
            db=db,
            asr_text=case["asr_text"],
            formatted_text=case["formatted_text"],
        )

        latency_ms = (time.perf_counter() - start) * 1000
        
        model_calls = 0
        embedding_calls = 0
        estimated_cost = 0.0

        actual_text = result["memory_aware_text"]

        if result["decisions"]:
            actual_decision = "intervene"
        else:
            actual_decision = "do_not_intervene"

        return {
            "case_id": case["case_id"],
            "description": case["description"],
            "asr_text": case["asr_text"],
            "formatted_text": case["formatted_text"],
            "expected_text": case["expected_text"],
            "actual_text": actual_text,
            "expected_decision": case["expected_decision"],
            "actual_decision": actual_decision,
            "text_match": actual_text == case["expected_text"],
            "decision_match": (
                actual_decision == case["expected_decision"]
            ),
            "passed": (
                actual_text == case["expected_text"]
                and actual_decision == case["expected_decision"]
            ),
            "decisions": result["decisions"],
            "trace": result["trace"],
            "alignment": result["alignment"],
            "latency_ms": round(latency_ms, 3),
            "model_calls": model_calls,
            "embedding_calls": embedding_calls,
            "estimated_cost": estimated_cost,
        }

    finally:
        db.close()

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Kivi memory evaluation."
    )
    parser.add_argument(
        "--dataset",
        default="cases.json",
        help="Evaluation dataset filename.",
    )
    parser.add_argument(
        "--output",
        default="results.json",
        help="Output results filename.",
    )

    args = parser.parse_args()

    cases_file = BASE_DIR / args.dataset
    results_file = BASE_DIR / args.output

    with open(cases_file, "r", encoding="utf-8") as file:
        cases = json.load(file)

    results = []

    for case in cases:
        result = run_case(case)
        results.append(result)

        status = "PASS" if result["passed"] else "FAIL"
        print(
            f"{status} | "
            f"{result['case_id']} | "
            f"{result['latency_ms']} ms"
        )

    passed = sum(result["passed"] for result in results)
    total = len(results)
    
    latencies = [
        result["latency_ms"]
        for result in results
    ]

    average_latency = (
        sum(latencies) / len(latencies)
        if latencies
        else 0
    )

    sorted_latencies = sorted(latencies)

    if sorted_latencies:
        p95_index = min(
            len(sorted_latencies) - 1,
            int(0.95 * len(sorted_latencies)),
        )
        p95_latency = sorted_latencies[p95_index]
    else:
        p95_latency = 0

    expected_interventions = sum(
        result["expected_decision"] == "intervene"
        for result in results
    )

    actual_interventions = sum(
        result["actual_decision"] == "intervene"
        for result in results
    )

    correct_interventions = sum(
        result["expected_decision"] == "intervene"
        and result["actual_decision"] == "intervene"
        for result in results
    )

    false_interventions = sum(
        result["expected_decision"] == "do_not_intervene"
        and result["actual_decision"] == "intervene"
        for result in results
    )

    missed_interventions = sum(
        result["expected_decision"] == "intervene"
        and result["actual_decision"] == "do_not_intervene"
        for result in results
    )

    intervention_precision = (
        correct_interventions / actual_interventions
        if actual_interventions
        else 0
    )

    intervention_recall = (
        correct_interventions / expected_interventions
        if expected_interventions
        else 0
    )

    summary = {
        "dataset": args.dataset,
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": total - passed,
        "accuracy": round(passed / total, 3) if total else 0,
        "expected_interventions": expected_interventions,
        "actual_interventions": actual_interventions,
        "correct_interventions": correct_interventions,
        "false_interventions": false_interventions,
        "missed_interventions": missed_interventions,
        "intervention_precision": round(intervention_precision, 3),
        "intervention_recall": round(intervention_recall, 3),
        "results": results,
        
        "average_latency_ms": round(average_latency, 3),
        "p95_latency_ms": round(p95_latency, 3),
        "model_calls": sum(
            result["model_calls"]
            for result in results
        ),
        "embedding_calls": sum(
            result["embedding_calls"]
            for result in results
        ),
        "estimated_cost": round(
            sum(result["estimated_cost"] for result in results),
            6,
        ),
    }

    with open(results_file, "w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2)

    print()
    print(f"Passed: {passed}/{total}")
    print(f"Accuracy: {summary['accuracy']}")
    
    print(
        f"Expected interventions: "
        f"{summary['expected_interventions']}"
    )
    print(
        f"Actual interventions: "
        f"{summary['actual_interventions']}"
    )
    print(
        f"False interventions: "
        f"{summary['false_interventions']}"
    )
    print(
        f"Missed interventions: "
        f"{summary['missed_interventions']}"
    )
    print(
        f"Intervention precision: "
        f"{summary['intervention_precision']}"
    )
    print(
        f"Intervention recall: "
        f"{summary['intervention_recall']}"
    )
    
    print(
        f"Average latency: "
        f"{summary['average_latency_ms']} ms"
    )
    print(
        f"P95 latency: "
        f"{summary['p95_latency_ms']} ms"
    )
    print(
        f"Model calls: "
        f"{summary['model_calls']}"
    )
    print(
        f"Embedding calls: "
        f"{summary['embedding_calls']}"
    )
    print(
        f"Estimated cost: "
        f"${summary['estimated_cost']}"
    )
    print(f"Results saved to: {results_file}")


if __name__ == "__main__":
    main()
