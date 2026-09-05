import re
from difflib import SequenceMatcher
from sqlalchemy.orm import Session

from app.services.memory_service import (
    decide_memory_intervention,
    find_candidates,
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


def format_with_memory(
    db: Session,
    asr_text: str,
    formatted_text: str,
) -> dict:
    """
    Apply learned personal memories to formatted text.

    Returns both:
    - decisions: actual interventions
    - trace: every memory decision considered
    """
    
    alignment = align_tokens(
        asr_text,
        formatted_text,
    )

    decisions: list[dict] = []
    trace: list[dict] = []

    def replace_word(match: re.Match[str]) -> str:
        word = match.group(0)

        candidates = find_candidates(
            db=db,
            observed_form=word,
        )

        decision = decide_memory_intervention(candidates,observed_form=word)

        trace_entry = {
            "observed_form": word,
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

            if replacement == word:
                return word

            decisions.append(
                {
                    "observed_form": word,
                    "replacement": replacement,
                    "decision": "intervene",
                    "memory_id": decision["memory_id"],
                    "confidence": decision["confidence"],
                    "similarity_score": decision["similarity_score"],
                    "margin": decision["margin"],
                    "reason": decision["reason"],
                }
            )

            return replacement

        return word

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