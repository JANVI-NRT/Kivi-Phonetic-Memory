from pydantic import BaseModel, Field


class MemoryCreate(BaseModel):
    spoken_form: str = Field(min_length=1, max_length=255)
    preferred_form: str = Field(min_length=1, max_length=255)
    context: str | None = None
    language: str | None = None

class ObservationCreate(BaseModel):
    observed_form: str = Field(min_length=1, max_length=255)
    preferred_form: str = Field(min_length=1, max_length=255)
    context: str | None = None
    language: str | None = None


class MemoryResponse(BaseModel):
    id: int
    spoken_form: str
    preferred_form: str
    context: str | None
    language: str | None
    confidence: float
    evidence_count: int

    model_config = {"from_attributes": True}

class FormatRequest(BaseModel):
    asr_text: str = Field(min_length=1)
    formatted_text: str = Field(min_length=1)


class FormatResponse(BaseModel):
    asr_text: str
    formatted_text: str
    memory_aware_text: str
    decisions: list[dict]
    trace: list[dict]
    alignment: list[dict]
