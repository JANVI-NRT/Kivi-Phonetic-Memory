import json
import time
from pathlib import Path

from app.database import SessionLocal
from app.models import Memory, Observation
from app.services.formatting_service import format_with_memory
from app.services.memory_service import learn_memory

BASE_DIR = Path(__file__).resolve().parent
CASES_FILE = BASE_DIR / "test_cases.json"
RESULTS_FILE = BASE_DIR / "results.json"


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
        }

    finally:
        db.close()


def main() -> None:
    with open(CASES_FILE, "r", encoding="utf-8") as file:
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

    summary = {
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": total - passed,
        "accuracy": round(passed / total, 3) if total else 0,
        "results": results,
    }

    with open(RESULTS_FILE, "w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2)

    print()
    print(f"Passed: {passed}/{total}")
    print(f"Accuracy: {summary['accuracy']}")
    print(f"Results saved to: {RESULTS_FILE}")


if __name__ == "__main__":
    main()