import argparse
import json
import statistics
import time
from pathlib import Path

from datasets import load_dataset
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.services.memory_service import (
    decide_memory_intervention,
    find_candidates,
    learn_memory,
)


def seed_profile(db) -> None:
    """Seed a fixed personal-memory profile for external robustness testing."""
    cases_path = Path(__file__).with_name("cases.json")

    with cases_path.open("r", encoding="utf-8") as file:
        cases = json.load(file)

    seen: set[tuple[str, str]] = set()

    for case in cases:
        pair = (
            case["asr_text"].strip(),
            case["formatted_text"].strip(),
        )

        if pair in seen:
            continue

        seen.add(pair)

        learn_memory(
            db=db,
            spoken_form=pair[0],
            preferred_form=pair[1],
        )


def percentile(
    values: list[float],
    percentile_value: float,
) -> float:
    if not values:
        return 0.0

    values = sorted(values)

    index = (len(values) - 1) * percentile_value
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)

    if lower == upper:
        return values[lower]

    fraction = index - lower

    return (
        values[lower]
        + (values[upper] - values[lower]) * fraction
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate Kivi against the held-out RED-ACE test set."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=11099,
    )

    args = parser.parse_args()

    dataset = load_dataset(
        "google/red_ace_asr_error_detection_and_correction",
        split="test",
    )

    limit = min(args.limit, len(dataset))

    # ---------------------------------------------------------
    # Create a fresh isolated in-memory database.
    # The user's real kivi.db is never modified.
    # ---------------------------------------------------------

    eval_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    EvalSessionLocal = sessionmaker(
        bind=eval_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    Base.metadata.create_all(bind=eval_engine)

    db = EvalSessionLocal()

    try:
        # -----------------------------------------------------
        # Seed only the fixed personal profile.
        # RED-ACE truth is NOT added to memory.
        # -----------------------------------------------------

        seed_profile(db)

        # -----------------------------------------------------
        # Evaluation metrics
        # -----------------------------------------------------

        total_examples = 0
        total_tokens = 0
        total_errors = 0
        candidate_hits = 0
        interventions = 0
        error_interventions = 0
        correct_interventions = 0

        latencies_ms: list[float] = []
        results: list[dict] = []

        # -----------------------------------------------------
        # Cache candidate retrieval across the entire dataset.
        #
        # The evaluation memory profile is fixed, so the same
        # ASR word will always produce the same candidates.
        # -----------------------------------------------------

        candidate_cache: dict[str, list] = {}

        # -----------------------------------------------------
        # Evaluate examples
        # -----------------------------------------------------

        for row in dataset.select(range(limit)):
            asr_words = row["asr_hypothesis"]
            labels = row["error_labels"]

            example_errors = 0
            example_candidates = 0
            example_interventions = 0

            for asr_word, label in zip(asr_words, labels):
                total_tokens += 1

                is_error = label == "1"

                if is_error:
                    total_errors += 1
                    example_errors += 1

                # -------------------------------------------------
                # Candidate retrieval
                # -------------------------------------------------

                start = time.perf_counter()

                cache_key = asr_word.strip().lower()

                if cache_key not in candidate_cache:
                    candidate_cache[cache_key] = find_candidates(
                        db=db,
                        observed_form=asr_word,
                        limit=5,
                    )

                candidates = candidate_cache[cache_key]

                # -------------------------------------------------
                # Decision
                # -------------------------------------------------

                decision = decide_memory_intervention(
                    candidates=candidates,
                    observed_form=asr_word,
                )

                # -------------------------------------------------
                # Latency
                # -------------------------------------------------

                latency_ms = (
                    time.perf_counter() - start
                ) * 1000

                latencies_ms.append(latency_ms)

                # -------------------------------------------------
                # Candidate statistics
                # -------------------------------------------------

                if candidates:
                    candidate_hits += 1
                    example_candidates += 1

                # -------------------------------------------------
                # Intervention statistics
                # -------------------------------------------------

                if decision["decision"] == "intervene":
                    interventions += 1
                    example_interventions += 1

                    if is_error:
                        error_interventions += 1
                    else:
                        correct_interventions += 1

            total_examples += 1

            results.append(
                {
                    "id": row["id"],
                    "error_tokens": example_errors,
                    "candidate_hits": example_candidates,
                    "interventions": example_interventions,
                }
            )

        # ---------------------------------------------------------
        # Metrics
        # ---------------------------------------------------------

        average_latency = (
            statistics.mean(latencies_ms)
            if latencies_ms
            else 0.0
        )

        p95_latency = percentile(
            latencies_ms,
            0.95,
        )

        safe_non_intervention_rate = (
            (total_tokens - interventions) / total_tokens
            if total_tokens
            else 0.0
        )

        false_intervention_rate = (
            correct_interventions / total_tokens
            if total_tokens
            else 0.0
        )

        # ---------------------------------------------------------
        # Output
        # ---------------------------------------------------------

        output = {
            "dataset": (
                "google/"
                "red_ace_asr_error_detection_and_correction"
            ),
            "split": "test",
            "examples_evaluated": total_examples,
            "total_asr_tokens": total_tokens,
            "asr_error_tokens": total_errors,
            "candidate_hits": candidate_hits,
            "interventions": interventions,
            "interventions_on_error_tokens": (
                error_interventions
            ),
            "interventions_on_correct_tokens": (
                correct_interventions
            ),
            "safe_non_intervention_rate": round(
                safe_non_intervention_rate,
                6,
            ),
            "false_intervention_rate": round(
                false_intervention_rate,
                6,
            ),
            "average_latency_ms": round(
                average_latency,
                3,
            ),
            "p95_latency_ms": round(
                p95_latency,
                3,
            ),
            "model_calls": 0,
            "embedding_calls": 0,
            "estimated_cost_usd": 0.0,
            "results": results,
        }

        output_path = Path(__file__).with_name(
            "external_results.json"
        )

        with output_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                output,
                file,
                indent=2,
            )

        # ---------------------------------------------------------
        # Console summary
        # ---------------------------------------------------------

        print()
        print(f"Examples evaluated: {total_examples}")
        print(f"ASR tokens: {total_tokens}")
        print(f"ASR errors: {total_errors}")
        print(
            "Errors with Kivi candidates: "
            f"{candidate_hits}"
        )
        print(
            "Kivi interventions: "
            f"{interventions}"
        )
        print(
            "Interventions on error tokens: "
            f"{error_interventions}"
        )
        print(
            "Interventions on correct tokens: "
            f"{correct_interventions}"
        )
        print(
            "Safe non-intervention rate: "
            f"{safe_non_intervention_rate:.4f}"
        )
        print(
            "False intervention rate: "
            f"{false_intervention_rate:.6f}"
        )
        print(
            "Average latency: "
            f"{average_latency:.3f} ms"
        )
        print(
            "P95 latency: "
            f"{p95_latency:.3f} ms"
        )
        print("Model calls: 0")
        print("Embedding calls: 0")
        print("Estimated cost: $0.0")
        print(
            f"Unique cached ASR words: "
            f"{len(candidate_cache)}"
        )
        print(
            f"Results saved to: {output_path}"
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()