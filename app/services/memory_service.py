from functools import lru_cache

from rapidfuzz.fuzz import ratio
from sqlalchemy.orm import Session

from app.models import Memory, MemoryCandidate, Observation


def normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    return " ".join(text.lower().strip().split())

def soundex(text: str) -> str:
    """
    Generate a simple Soundex code.

    Soundex keeps the first letter and encodes
    consonant sounds using digits.
    """

    text = normalize_text(text)

    if not text:
        return ""

    text = "".join(
        character for character in text
        if character.isalpha()
    )

    if not text:
        return ""

    mapping = {
        "b": "1",
        "f": "1",
        "p": "1",
        "v": "1",
        "c": "2",
        "g": "2",
        "j": "2",
        "k": "2",
        "q": "2",
        "s": "2",
        "x": "2",
        "z": "2",
        "d": "3",
        "t": "3",
        "l": "4",
        "m": "5",
        "n": "5",
        "r": "6",
    }

    first_letter = text[0].upper()

    encoded = []
    previous_code = mapping.get(text[0], "")

    for character in text[1:]:
        code = mapping.get(character, "")

        if code and code != previous_code:
            encoded.append(code)

        previous_code = code

    return (first_letter + "".join(encoded) + "000")[:4]

def normalize_language(language: str | None) -> str:
    """Convert common language codes to eSpeak-compatible codes."""

    if not language:
        return "en-us"

    normalized = language.lower().strip()

    language_map = {
        "en": "en-us",
        "english": "en-us",
    }

    return language_map.get(normalized, normalized)

def phonetic_similarity(
    observed_form: str,
    preferred_form: str,
    language: str = "en-us",
) -> float:
    language = normalize_language(language)
    observed_phonemes = to_phonemes(
        observed_form,
        language=language,
    )

    preferred_phonemes = to_phonemes(
        preferred_form,
        language=language,
    )

    if not observed_phonemes or not preferred_phonemes:
        return 0.0

    return float(
        ratio(
            observed_phonemes,
            preferred_phonemes,
        )
    )

def find_existing_memory(
    db: Session,
    preferred_form: str,
) -> Memory | None:
    """Find an existing memory with the same preferred form."""

    normalized_target = normalize_text(preferred_form)

    memories = db.query(Memory).all()

    for memory in memories:
        if normalize_text(memory.preferred_form) == normalized_target:
            return memory

    return None

def has_observed_form(
    observations: list[Observation],
    memory_id: int,
    observed_form: str,
) -> bool:
    normalized_observed = normalize_text(observed_form)

    return any(
        observation.memory_id == memory_id
        and normalize_text(observation.observed_form) == normalized_observed
        for observation in observations
    )

def find_candidates(
    db: Session,
    observed_form: str,
    limit: int = 5,
) -> list[tuple[Memory, float, float, str, bool]]:
    """
    Find candidate memories using fuzzy retrieval first, then
    phonetic similarity only for the strongest fuzzy matches.
    """

    normalized_observed = normalize_text(observed_form)

    memories = db.query(Memory).all()
    observations = db.query(Observation).all()

    observations_by_memory: dict[int, list[str]] = {}

    for observation in observations:
        observations_by_memory.setdefault(
            observation.memory_id,
            [],
        ).append(observation.observed_form)

    # First pass: cheap fuzzy retrieval.
    fuzzy_candidates: list[
        tuple[Memory, float, str, bool]
    ] = []

    for memory in memories:
        forms = [memory.preferred_form]
        forms.extend(
            observations_by_memory.get(memory.id, [])
        )

        best_fuzzy = 0.0
        best_form = ""

        for form in forms:
            normalized_form = normalize_text(form)

            fuzzy_score = ratio(
                normalized_observed,
                normalized_form,
            )

            if fuzzy_score > best_fuzzy:
                best_fuzzy = fuzzy_score
                best_form = form

        if best_fuzzy >= 35:
            fuzzy_candidates.append(
                (
                    memory,
                    best_fuzzy,
                    best_form,
                    has_observed_form(
                        observations,
                        memory.id,
                        observed_form,
                    ),
                )
            )

    # Keep only the strongest fuzzy candidates before
    # doing expensive phonetic comparisons.
    fuzzy_candidates.sort(
        key=lambda item: item[1],
        reverse=True,
    )

    phonetic_pool = fuzzy_candidates[:20]

    candidates: list[
        tuple[Memory, float, float, str, bool]
    ] = []

    for (
        memory,
        fuzzy_score,
        best_form,
        direct_evidence,
    ) in phonetic_pool:

        phonetic_score = phonetic_similarity(
            normalized_observed,
            normalize_text(best_form),
            language=memory.language or "en-us",
        )

        combined_score = (
            0.6 * fuzzy_score
            + 0.4 * phonetic_score
        )

        if combined_score >= 50:
            candidates.append(
                (
                    memory,
                    fuzzy_score,
                    phonetic_score,
                    best_form,
                    direct_evidence,
                )
            )

    candidates.sort(
        key=lambda item: (
            0.6 * item[1] + 0.4 * item[2]
        ),
        reverse=True,
    )

    return candidates[:limit]

def learn_memory(
    db: Session,
    spoken_form: str,
    preferred_form: str,
    context: str | None = None,
    language: str | None = None,
) -> Memory:
    """
    Learn a term from an observation.

    If the preferred form already exists, add evidence to that
    memory instead of creating a duplicate.
    """

    memory = find_existing_memory(db, preferred_form)

    if memory is None:
        memory = Memory(
            spoken_form=spoken_form,
            preferred_form=preferred_form,
            context=context,
            language=language,
            confidence=0.5,
            evidence_count=1,
        )

        db.add(memory)
        db.flush()

    else:
        memory.evidence_count += 1

        # Increase confidence gradually as more evidence arrives.
        memory.confidence = min(
            0.95,
            memory.confidence + 0.1,
        )

    observation = Observation(
        memory_id=memory.id,
        observed_form=spoken_form,
        evidence_type="positive",
    )

    db.add(observation)
    db.commit()
    db.refresh(memory)

    return memory


def promote_candidate(
    db: Session,
    candidate_id: int,
) -> Memory:
    candidate = (
        db.query(MemoryCandidate)
        .filter(MemoryCandidate.id == candidate_id)
        .first()
    )

    if candidate is None:
        raise ValueError("Candidate not found.")

    if candidate.status == "promoted":
        raise ValueError("Candidate is already promoted.")

    # A candidate must have explicit confirmation before
    # becoming trusted memory.
    memory = find_existing_memory(
        db,
        candidate.possible_preferred_form,
    )

    if memory is None:
        memory = Memory(
            spoken_form=candidate.observed_form,
            preferred_form=candidate.possible_preferred_form,
            context=candidate.context,
            language=candidate.language,
            confidence=0.9,
            evidence_count=candidate.evidence_count,
        )
        db.add(memory)
        db.flush()
    else:
        memory.confidence = max(memory.confidence, 0.9)
        memory.evidence_count += candidate.evidence_count

    candidate.status = "promoted"

    db.commit()
    db.refresh(memory)

    return memory


def reject_candidate(
    db: Session,
    candidate_id: int,
) -> MemoryCandidate:
    candidate = (
        db.query(MemoryCandidate)
        .filter(MemoryCandidate.id == candidate_id)
        .first()
    )

    if candidate is None:
        raise ValueError("Candidate not found.")

    if candidate.status == "promoted":
        raise ValueError("Promoted candidates cannot be rejected.")

    candidate.status = "rejected"

    db.commit()
    db.refresh(candidate)

    return candidate


def decide_memory_intervention(
    candidates: list[tuple[Memory, float, float, str, bool]], observed_form: str,
) -> dict:
    if not candidates:
        return {
            "decision": "do_not_intervene",
            "memory_id": None,
            "replacement": None,
            "confidence": 0.0,
            "similarity_score": 0.0,
            "margin": None,
            "direct_evidence": False,
            "reason": "No memory candidates found.",
        }

    best_memory, best_fuzzy, best_phonetic, _ , direct_evidence = candidates[0]

    best_similarity = (
        0.6 * best_fuzzy
        + 0.4 * best_phonetic
    )

    final_confidence = (
            0.7 * (best_similarity / 100)
            + 0.3 * best_memory.confidence
        )

    if normalize_text(observed_form) == normalize_text(best_memory.preferred_form):
        return {
            "decision": "do_not_intervene",
            "memory_id": best_memory.id,
            "replacement": None,
            "confidence": round(final_confidence, 3),
            "similarity_score": 100.0,
            "margin": None,
            "direct_evidence": direct_evidence,
            "reason": "Formatted text already matches the preferred form exactly.",
        }



    # Basic similarity check.
    if best_similarity < 60:
        return {
            "decision": "do_not_intervene",
            "memory_id": best_memory.id,
            "replacement": None,
            "confidence": round(final_confidence, 3),
            "similarity_score": round(best_similarity, 2),
            "margin": None,
            "direct_evidence": direct_evidence,
            "reason": "Similarity is too weak.",
        }

    # Memory confidence check.
    if best_memory.confidence < 0.5:
        return {
            "decision": "do_not_intervene",
            "memory_id": best_memory.id,
            "replacement": None,
            "confidence": round(final_confidence, 3),
            "similarity_score": round(best_similarity, 2),
            "margin": None,
            "direct_evidence": direct_evidence,
            "reason": "Memory confidence is too low.",
        }

    # Ambiguity check.
    margin = None

    if len(candidates) >= 2:
        _ , second_fuzzy, second_phonetic, _ , _ = candidates[1]

        second_similarity = (
            0.6 * second_fuzzy
            + 0.4 * second_phonetic
        )


        margin = best_similarity - second_similarity

        if second_similarity >= 60 and margin < 10:
            return {
                "decision": "do_not_intervene",
                "memory_id": None,
                "replacement": None,
                "confidence": round(final_confidence, 3),
                "similarity_score": round(best_similarity, 2),
                "margin": round(margin, 2),
                "direct_evidence": direct_evidence,
                "reason": "Multiple memory candidates are similarly strong.",
            }
    if not direct_evidence and best_similarity < 85:
        return {
            "decision": "do_not_intervene",
            "memory_id": best_memory.id,
            "replacement": None,
            "confidence": round(final_confidence, 3),
            "similarity_score": round(best_similarity, 2),
            "margin": round(margin, 2) if margin is not None else None,
            "direct_evidence": direct_evidence,
            "reason": "Similarity is strong, but this observed form has not been learned as evidence for the memory.",
        }


    return {
        "decision": "intervene",
        "memory_id": best_memory.id,
        "replacement": best_memory.preferred_form,
        "confidence": round(final_confidence, 3),
        "similarity_score": round(best_similarity, 2),
        "margin": round(margin, 2) if margin is not None else None,
        "direct_evidence": direct_evidence,
        "reason":  (
            "Strong similarity supported by directly learned evidence."
            if direct_evidence
            else "Strong similarity to the stored preferred form."
        ),

    }


from phonemizer import phonemize


@lru_cache(maxsize=1000)
def to_phonemes(text: str, language: str = "en-us") -> str:
    return phonemize(
        text,
        backend="espeak",
        language=language,
        strip=True,
    )

def learn_candidate(
    db: Session,
    observed_form: str,
    possible_preferred_form: str,
    context: str | None = None,
    language: str | None = None,
    evidence_type: str = "asr_formatted_substitution",
) -> MemoryCandidate:
    candidates = db.query(MemoryCandidate).all()
    candidate = next(
        (
            existing
            for existing in candidates
            if normalize_text(existing.observed_form)
            == normalize_text(observed_form)
            and normalize_text(existing.possible_preferred_form)
            == normalize_text(possible_preferred_form)
        ),
        None,
    )


    if candidate is None:
        candidate = MemoryCandidate(
            observed_form=observed_form,
            possible_preferred_form=possible_preferred_form,
            context=context,
            language=language,
            confidence=0.0,
            importance=0.5,
            risk_level="high",
            evidence_count=1,
            evidence_type=evidence_type,
            evidence_source="observation",
            status="candidate",
        )
        db.add(candidate)
    else:
        candidate.evidence_count += 1

    db.commit()
    db.refresh(candidate)

    return candidate

