# Kivi — RUN.md

This file is the reproducible local run guide for the Kivi phonetic-memory project.

## 1. Requirements

- Windows, Linux, or macOS
- Python 3.11
- Git
- eSpeak NG installed and available on `PATH`
- Internet access only for the external RED-ACE evaluation

The application itself does not require an LLM API key, embedding API key, or other secret.

## 2. Clone

```powershell
git clone https://github.com/JANVI-NRT/Kivi-Phonetic-Memory.git
cd Kivi-Phonetic-Memory
```

## 3. Create and activate the virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Check the runtime:

```powershell
python --version
```

Expected major/minor version:

```text
Python 3.11.x
```

## 4. Install dependencies

Install the direct Python dependencies used by the project:

```powershell
python -m pip install --upgrade pip
python -m pip install fastapi uvicorn sqlalchemy pydantic alembic rapidfuzz phonemizer datasets
```

For development checks:

```powershell
python -m pip install ruff
```

The project uses eSpeak through `phonemizer`, so eSpeak NG must also be installed separately and available on `PATH`.

Verify phonemizer:

```powershell
python -c "from phonemizer import phonemize; print(phonemize('hello', backend='espeak', language='en-us'))"
```

## 5. Create/update the database schema

From the repository root:

```powershell
alembic upgrade head
```

The application uses SQLite at:

```text
sqlite:///./kivi.db
```

The database file is ignored by Git. The schema is reproducible from the committed Alembic migrations.

## 6. Start the application

```powershell
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

The root route serves the browser interface.

## 7. Browser demo

Use the UI in this order:

1. **Teach Kivi** — add a spoken form and preferred form.
2. **Memory State** — inspect trusted memories and learning candidates.
3. **Format Text** — enter ASR and formatted text.
4. **Decision Trace** — inspect retrieval, similarity, confidence, and intervention reason.
5. **Reset** — clear memory and repeat the demo.

A useful example is to first teach a personal spelling and then submit an ASR/formatted pair using the spoken variant.

## 8. API smoke test

With the server running, teach a memory:

```powershell
$body = @{
    spoken_form = "Moohit"
    preferred_form = "Mohit"
    context = "person name"
    language = "en-us"
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri http://127.0.0.1:8000/memories `
    -ContentType "application/json" `
    -Body $body
```

Then format text:

```powershell
$body = @{
    asr_text = "Ask Moohit to join."
    formatted_text = "Ask Moohit to join."
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri http://127.0.0.1:8000/format `
    -ContentType "application/json" `
    -Body $body
```

The response includes:

- `memory_aware_text`
- `decisions`
- `trace`
- `alignment`

## 9. Reset memory

PowerShell:

```powershell
Invoke-RestMethod `
    -Method Post `
    -Uri http://127.0.0.1:8000/memories/reset
```

Alternatively use the Reset control in the browser UI.

## 10. Run the internal evaluation

From the repository root:

```powershell
python evaluation/run_evaluation.py
```

The evaluator resets and seeds memory separately for each case using the memory setup in `evaluation/cases.json`.

Generated output:

```text
evaluation/results.json
```

Current expected summary:

```text
Passed: 20/20
Accuracy: 1.0
Intervention precision: 1.0
Intervention recall: 1.0
False interventions: 0
Missed interventions: 0
Model calls: 0
Embedding calls: 0
Estimated cost: $0.0
```

## 11. Run the external RED-ACE evaluation

```powershell
python evaluation/run_external_evaluation.py
```

This downloads/loads the Google RED-ACE dataset through Hugging Face `datasets`.

The evaluator uses an isolated in-memory SQLite database and a fixed personal profile. It does not put RED-ACE truth labels into Kivi memory.

Generated output:

```text
evaluation/external_results.json
```

Current expected summary:

```text
Examples evaluated: 11099
ASR tokens: 207714
ASR errors: 24247
Errors with Kivi candidates: 212
Kivi interventions: 0
Interventions on error tokens: 0
Interventions on correct tokens: 0
Safe non-intervention rate: 1.0000
False intervention rate: 0.000000
Average latency: 0.136 ms
P95 latency: 1.571 ms
Model calls: 0
Embedding calls: 0
Estimated cost: $0.0
```

## 12. Run tests and static checks

```powershell
python test_decisions.py
python -m compileall app evaluation
ruff check .
git diff --check
```

Expected:

```text
ruff check .
All checks passed!
```

`test_decisions.py` writes `decision_results.json`, which is ignored by Git.

## 13. Reproducibility

The repository contains:

- Alembic migrations for the database schema.
- `evaluation/cases.json` containing reproducible internal cases and per-case memory setup.
- `evaluation/results.json` containing generated internal results.
- `evaluation/external_results.json` containing generated RED-ACE results.
- evaluation scripts used to regenerate the result files.

No secrets are required.

There is no `.env.example` because the current implementation does not require environment variables or API credentials.

## 14. Troubleshooting

### PowerShell blocks virtual-environment activation

Run PowerShell with the appropriate execution-policy permission, then:

```powershell
.\.venv\Scripts\Activate.ps1
```

### `phonemizer` cannot find eSpeak

Check:

```powershell
where.exe espeak-ng
```

If it returns a path, eSpeak is visible to the shell.

Then retry:

```powershell
python -c "from phonemizer import phonemize; print(phonemize('hello', backend='espeak', language='en-us'))"
```

### Database needs a clean reset

For normal use, prefer the application reset endpoint:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/memories/reset
```

For a completely fresh local database:

```powershell
Remove-Item .\kivi.db -ErrorAction SilentlyContinue
alembic upgrade head
```

### External evaluation cannot download RED-ACE

The external benchmark requires network access because the dataset is loaded through Hugging Face `datasets`. The main browser application and internal evaluation do not depend on RED-ACE being available.

## 15. No credentials

The current project has:

- no required `.env`
- no LLM API key
- no embedding API key
- no hosted URL
- no external application credentials

The application is intended to run locally.
