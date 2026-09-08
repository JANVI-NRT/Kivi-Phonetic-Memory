from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Memory, MemoryCandidate, Observation
from app.schemas import (
    FormatRequest,
    FormatResponse,
    MemoryCreate,
    MemoryResponse,
    ObservationCreate,
)
from app.services.formatting_service import format_with_memory
from app.services.memory_service import (
    decide_memory_intervention,
    find_candidates,
    learn_memory,
    promote_candidate,
    reject_candidate,
)

app = FastAPI(title="Kivi Phonetic Memory")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
def root():
    return FileResponse("app/static/index.html")


@app.post("/memories", response_model=MemoryResponse)
def create_memory(
    memory: MemoryCreate,
    db: Session = Depends(get_db),
):
    return learn_memory(
        db=db,
        spoken_form=memory.spoken_form,
        preferred_form=memory.preferred_form,
        context=memory.context,
        language=memory.language,
    )

@app.get("/memories/search")
def search_memories(
    q: str,
    db: Session = Depends(get_db),
):
    candidates = find_candidates(
        db=db,
        observed_form=q,
    )

    return [
    {
        "id": memory.id,
        "preferred_form": memory.preferred_form,
        "fuzzy_score": round(fuzzy_score, 2),
        "phonetic_score": round(phonetic_score, 2),
    }
    for memory, fuzzy_score, phonetic_score in candidates
]


@app.get("/memories/decide")
def decide_memory(
    q: str,
    db: Session = Depends(get_db),
):
    candidates = find_candidates(
        db=db,
        observed_form=q,
    )

    decision = decide_memory_intervention(candidates,q)

    return {
        "observed_form": q,
        "decision": decision,
        "candidates": [
            {
                "id": memory.id,
                "preferred_form": memory.preferred_form,
                "fuzzy_score": round(fuzzy_score, 2),
                "phonetic_score": round(phonetic_score, 2),
                "memory_confidence": memory.confidence,
                "evidence_count": memory.evidence_count,
                "matched_form": matched_form,
                "direct_evidence": direct_evidence,
            }
            for memory, fuzzy_score, phonetic_score, matched_form, direct_evidence in candidates
        ],
    }

@app.post("/format", response_model=FormatResponse)
def format_text(
    request: FormatRequest,
    db: Session = Depends(get_db),
):
    result = format_with_memory(
        db=db,
        asr_text=request.asr_text,
        formatted_text=request.formatted_text,
    )

    return {
        "asr_text": request.asr_text,
        "formatted_text": request.formatted_text,
        "memory_aware_text": result["memory_aware_text"],
        "decisions": result["decisions"],
        "trace": result["trace"],
        "alignment": result["alignment"],
    }

@app.get("/memories", response_model=list[MemoryResponse])
def get_memories(
    db: Session = Depends(get_db),
):
    return db.query(Memory).order_by(Memory.id).all()

@app.get("/candidates")
def get_candidates(db: Session = Depends(get_db)):
    return db.query(MemoryCandidate).order_by(MemoryCandidate.id).all()

@app.post("/memories/reset")
def reset_memories(
    db: Session = Depends(get_db),
):
    db.query(Observation).delete()
    db.query(Memory).delete()
    db.commit()

    return {
        "message": "All memories and observations have been reset."
    }

@app.post("/observations", response_model=MemoryResponse)
def create_observation(
    observation: ObservationCreate,
    db: Session = Depends(get_db),
):
    return learn_memory(
        db=db,
        spoken_form=observation.observed_form,
        preferred_form=observation.preferred_form,
        context=observation.context,
        language=observation.language,
    )

@app.post("/candidates/{candidate_id}/promote")
def promote_memory_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
):
    try:
        memory = promote_candidate(
            db=db,
            candidate_id=candidate_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return {
        "message": "Candidate promoted to trusted memory.",
        "memory": {
            "id": memory.id,
            "spoken_form": memory.spoken_form,
            "preferred_form": memory.preferred_form,
            "confidence": memory.confidence,
            "evidence_count": memory.evidence_count,
        },
    }

@app.post("/candidates/{candidate_id}/reject")
def reject_memory_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
):
    try:
        candidate = reject_candidate(
            db=db,
            candidate_id=candidate_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return {
        "message": "Candidate rejected.",
        "candidate": {
            "id": candidate.id,
            "observed_form": candidate.observed_form,
            "possible_preferred_form": candidate.possible_preferred_form,
            "status": candidate.status,
            "evidence_count": candidate.evidence_count,
        },
    }
