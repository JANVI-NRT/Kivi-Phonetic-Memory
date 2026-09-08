# Kivi — Phonetic Memory System

A small, inspectable memory layer for Kivi that learns how a person refers to important words and uses that memory to make formatting corrections only when the evidence is strong enough.

The system does **not** perform speech recognition. It accepts an ASR transcript and a formatted transcript, learns from the differences, retrieves relevant personal memories, and decides whether a memory should change the formatted output.

## Core idea

Kivi separates uncertain observations from trusted memories:

```text
ASR text + formatted text
          |
          v
   token alignment
          |
          +--> substitution evidence --> learning candidate
          |
          v
    memory retrieval
   fuzzy + phonetic
          |
          v
   decision engine
          |
      +---+---+
      |       |
 intervene   do_not_intervene
      |       |
      v       v
memory-aware formatted text
```

A candidate is not automatically trusted. The decision engine checks similarity, confidence, direct evidence, and ambiguity between competing candidates. This makes deliberate **no-intervention** a first-class outcome.

## What is implemented

- Personal memory CRUD using SQLite and SQLAlchemy.
- Word-level observations associated with memories.
- Learning candidates for uncertain ASR/formatted substitutions.
- Candidate confidence, importance, risk level, evidence type/source, and status.
- Candidate promotion and rejection.
- Text normalization.
- Fuzzy retrieval with RapidFuzz.
- Phonetic retrieval with eSpeak/phonemizer.
- Ambiguity checking using the score margin between top candidates.
- Decision traces explaining why Kivi intervened or did not intervene.
- Browser UI for teaching, inspecting memory, formatting text, reading traces, and resetting memory.
- Reproducible internal evaluation cases.
- External RED-ACE ASR robustness evaluation.
- No LLM or embedding calls in the current implementation.

## Why there is no RAG/LLM in the current MVP

The assignment asks for the smallest memory system that makes Kivi feel as though it has met the person before. The current system therefore uses a structured relational memory store plus deterministic retrieval and decision rules.

A vector database, embeddings, or an LLM could be added later if semantic retrieval becomes necessary, but adding them now would make the system harder to inspect and would not be justified by the current evaluation.

## Repository structure

```text
app/
  main.py
  database.py
  models.py
  schemas.py
  services/
    memory_service.py
    formatting_service.py
  static/
    index.html
    style.css
    app.js

migrations/
  versions/                 # Alembic database migrations

evaluation/
  cases.json                # reproducible internal cases + memory setup
  results.json              # generated internal evaluation results
  run_evaluation.py         # internal evaluation runner
  run_external_evaluation.py
                            # RED-ACE external robustness evaluation
  external_results.json     # generated external results

test_decisions.py           # decision-engine checks
alembic.ini
pyproject.toml
```

`kivi.db` is intentionally ignored by Git. The schema is recreated through Alembic migrations.

## Database model

### `memories`

Trusted personal memories.

Important fields:

- `spoken_form`
- `preferred_form`
- `context`
- `language`
- `confidence`
- `evidence_count`

### `observations`

Evidence associated with a memory.

Important fields:

- `memory_id`
- `observed_form`
- `evidence_type`

### `memory_candidates`

Potential mappings that have not yet earned trusted-memory status.

Important fields:

- `observed_form`
- `possible_preferred_form`
- `confidence`
- `importance`
- `risk_level`
- `evidence_count`
- `evidence_type`
- `evidence_source`
- `status`

Candidate statuses include candidate, promoted, and rejected.

## Retrieval and decision logic

Retrieval uses two signals:

1. **Fuzzy similarity** — inexpensive lexical similarity.
2. **Phonetic similarity** — eSpeak phoneme comparison for stronger fuzzy candidates.

Phonetic matching is treated as a retrieval signal, not proof of identity.

The intervention decision then applies safety gates:

- no candidate -> no intervention
- exact preferred form -> no intervention
- weak similarity -> no intervention
- insufficient trusted-memory confidence -> no intervention
- close competing candidates -> no intervention
- indirect evidence with insufficiently strong similarity -> no intervention
- otherwise -> intervene

The API returns a decision trace so the result is inspectable rather than being a hidden replacement rule.

## Main API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | Browser UI |
| POST | `/memories` | Teach a trusted memory |
| GET | `/memories` | Inspect trusted memories |
| GET | `/memories/search` | Search memory |
| GET | `/memories/decide` | Inspect intervention decision |
| POST | `/memories/reset` | Reset memories |
| GET | `/candidates` | Inspect learning candidates |
| POST | `/candidates/{id}/promote` | Promote candidate to memory |
| POST | `/candidates/{id}/reject` | Reject candidate |
| POST | `/observations` | Add observation |
| POST | `/format` | Produce memory-aware formatted text |

## Demo

Start the application as described in `RUN.md`.

A useful demo flow is:

1. Teach Kivi a personal term, for example a spoken form and preferred form.
2. Inspect the memory state.
3. Submit an ASR/formatted pair containing the observed form.
4. Inspect the memory-aware output and decision trace.
5. Repeat with an ambiguous or weakly supported case.
6. Verify that Kivi deliberately does not intervene.
7. Reset the memory and repeat.

## Evaluation

### Internal evaluation

The internal dataset contains 20 cases covering:

- exact personal terms
- phonetic variation
- spelling variation
- case/punctuation differences
- unknown terms
- similar but distinct names
- ambiguity
- weak similarity
- common words
- multiple personal terms
- longer sentences

Current generated result:

- Cases: 20
- Passed: 20/20
- Accuracy: 1.000
- Expected interventions: 9
- Actual interventions: 9
- False interventions: 0
- Missed interventions: 0
- Intervention precision: 1.000
- Intervention recall: 1.000
- Average latency: 58.827 ms
- P95 latency: 1040.437 ms
- Model calls: 0
- Embedding calls: 0
- Estimated cost: $0

Run it with:

```powershell
python evaluation/run_evaluation.py
```

### External RED-ACE evaluation

The project also evaluates safe behavior on Google's RED-ACE ASR Error Detection and Correction test split.

This is **not a personal-memory dataset**, so the result must not be interpreted as personal-name correction accuracy. Instead, it is an external robustness benchmark asking whether generic ASR text causes the personal-memory layer to intervene spuriously.

The evaluator:

- does not inject RED-ACE truth into Kivi memory
- uses an isolated in-memory SQLite database
- seeds a fixed personal profile independent of RED-ACE
- uses read-only retrieval/decision functions rather than the formatter's candidate-learning side effect
- caches repeated ASR-word retrievals for efficient evaluation

Current generated result:

- Examples: 11,099
- ASR tokens: 207,714
- ASR errors: 24,247
- Error tokens with Kivi candidates: 212
- Interventions: 0
- Interventions on error tokens: 0
- Interventions on correct tokens: 0
- Safe non-intervention rate: 1.000000
- False intervention rate: 0.000000
- Average latency: 0.136 ms
- P95 latency: 1.571 ms
- Model calls: 0
- Embedding calls: 0
- Estimated cost: $0
- Unique cached ASR words: 13,985

Run it with:

```powershell
python evaluation/run_external_evaluation.py
```

The RED-ACE dataset is downloaded by the Hugging Face `datasets` library, so the external evaluation requires network access.

## Testing and code quality

Run:

```powershell
python test_decisions.py
python -m compileall app evaluation
ruff check .
git diff --check
```

The current project passes Ruff and Python compilation checks.

## Limitations

- The current phonetic path defaults to English (`en-us`) unless a memory specifies another supported phonemizer language.
- Retrieval currently scans the relational memory tables and is intentionally simple for the MVP.
- The system does not use speech recognition.
- RED-ACE evaluates safe non-intervention, not personal-memory correction accuracy.
- There is no LLM/embedding dependency in the current implementation.
- The current SQLite database is local and ignored by Git; migrations and evaluation cases provide reproducibility.

## Design principle

> Build the smallest memory system that makes Kivi feel as though it has met this person before.

The implementation therefore prefers explicit evidence, inspectability, conservative intervention, and a useful explanation over a larger opaque memory stack.
