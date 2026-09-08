import re
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.services.memory_service import (
    decide_memory_intervention,
    find_candidates,
    learn_candidate,
)

WORD_PATTERN = re.compile(r"\b[\w'-]+\b")

def align_tokens(
    asr_text: str,
    formatted_text: str,
) -> list[dict]:
    """
    Align ASR tokens with formatted-text tokens.

    This gives us evidence about which formatted words
    came from which ASR words.
    """

    asr_tokens = re.findall(r"\b[\w'-]+\b", asr_text)
    formatted_tokens = re.findall(
        r"\b[\w'-]+\b",
        formatted_text,
    )

    matcher = SequenceMatcher(
        None,
        [token.lower() for token in asr_tokens],
        [token.lower() for token in formatted_tokens],
    )

    alignment: list[dict] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for asr_token, formatted_token in zip(
                asr_tokens[i1:i2],
                formatted_tokens[j1:j2],
            ):
                alignment.append(
                    {
                        "asr_token": asr_token,
                        "formatted_token": formatted_token,
                        "match": "exact",
                    }
                )

        elif tag == "replace":
            alignment.append(
                {
                    "asr_token": " ".join(asr_tokens[i1:i2]),
                    "formatted_token": " ".join(
                        formatted_tokens[j1:j2]
                    ),
                    "match": "replace",
                }
            )

        elif tag == "delete":
            alignment.append(
                {
                    "asr_token": " ".join(asr_tokens[i1:i2]),
                    "formatted_token": None,
                    "match": "delete",
                }
            )

        elif tag == "insert":
            alignment.append(
                {
                    "asr_token": None,
                    "formatted_token": " ".join(
                        formatted_tokens[j1:j2]
                    ),
                    "match": "insert",
                }
            )

    return alignment

def extract_candidate_pairs(alignment: list[dict]) -> list[dict]:
    pairs = []

    for item in alignment:
        if item["match"] != "replace":
            continue

        observed_form = item["asr_token"]
        possible_preferred_form = item["formatted_token"]

        if not observed_form or not possible_preferred_form:
            continue

        if observed_form.lower() == possible_preferred_form.lower():
            continue

        pairs.append(
            {
                "observed_form": observed_form,
                "possible_preferred_form": possible_preferred_form,
            }
        )

    return pairs

def format_with_memory(
    db: Session,
    asr_text: str,
    formatted_text: str,
) -> dict:
    """
    Apply trusted personal memories to the formatted text.

    Decisions are made from ASR -> formatted alignment pairs,
    including exact-alignment tokens that may still need memory correction.
    """

    alignment = align_tokens(
        asr_text,
        formatted_text,
    )

    decisions: list[dict] = []
    trace: list[dict] = []

    candidate_pairs = extract_candidate_pairs(alignment)

    # Learn new ASR -> formatted substitutions as candidates.
    for pair in candidate_pairs:
        learn_candidate(
            db=db,
            observed_form=pair["observed_form"],
            possible_preferred_form=pair["possible_preferred_form"],
            evidence_type="asr_formatted_substitution",
        )

    # Decide what to do with each ASR/formatted token pair.
    replacements: dict[str, str] = {}

    for item in alignment:
        observed_form = item["asr_token"]
        formatted_form = item["formatted_token"]

        # We only need memory reasoning when there is an actual
        # token on both sides.
        if not observed_form or not formatted_form:
            continue

        candidates = find_candidates(
            db=db,
            observed_form=observed_form,
        )

        decision = decide_memory_intervention(
            candidates,
            observed_form=observed_form,
        )

        trace_entry = {
            "observed_form": observed_form,
            "formatted_form": formatted_form,
            "decision": decision["decision"],
            "memory_id": decision["memory_id"],
            "direct_evidence": decision["direct_evidence"],
            "confidence": decision["confidence"],
            "similarity_score": decision["similarity_score"],
            "margin": decision["margin"],
            "reason": decision["reason"],
        }

        trace.append(trace_entry)

        if decision["decision"] == "intervene":
            replacement = decision["replacement"]

            if replacement != formatted_form:
                replacements[formatted_form] = replacement

                decisions.append(
                    {
                        "observed_form": observed_form,
                        "replacement": replacement,
                        "decision": "intervene",
                        "memory_id": decision["memory_id"],
                        "confidence": decision["confidence"],
                        "similarity_score": decision["similarity_score"],
                        "margin": decision["margin"],
                        "reason": decision["reason"],
                    }
                )

    def replace_word(match: re.Match[str]) -> str:
        word = match.group(0)
        return replacements.get(word, word)

    memory_aware_text = WORD_PATTERN.sub(
        replace_word,
        formatted_text,
    )

    return {
        "memory_aware_text": memory_aware_text,
        "decisions": decisions,
        "trace": trace,
        "alignment": alignment,
    }

if __name__ == "__main__":
    from app.database import SessionLocal

    db = SessionLocal()

    result = format_with_memory(
        db=db,
        asr_text="Ask Rahit to review the Sarvam Kivi service",
        formatted_text="Ask Rohit to review the Sarvam Kivi service.",
    )

    print(result)

    db.close()
