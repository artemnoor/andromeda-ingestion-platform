# Live BMSTU evaluation

`python scripts/live_bmstu_e2e.py --confirm-live-ai` is an opt-in, paid live
evaluation. It is deliberately separate from pytest, CI, and the demo seed.
The command checks the local AI configuration without printing the key, checks
both services and the Core ontology over HTTP, registers the curated sources,
fetches the real official documents, runs DeepSeek, validates evidence against
the exact prepared artifact, and verifies Core rule/provenance state. Its JSON
report is written under the git-ignored `reports/` directory. Each source is
reported independently; timeouts do not prevent later sources from running,
and the command exits non-zero if acceptance checks fail.

The committed evaluation manifest contains eight official BMSTU sources with
manually reviewed golden expectations. Five sources are live-run by default:
the IUK5 program page, 2026 curriculum PDF, entrance-exam page, official
Appendix 1 PDF, and admission-seats page. The linked
main Rules PDF endpoint (`api.www.bmstu.ru/file/117811/download`) returned HTTP
500 during verification, so the accessible official Appendix 1 PDF is used for
the regulatory vertical slice instead. No downloaded source documents are
committed; raw artifacts remain in the ignored local artifact store.

## Local stack (PowerShell)

Use an isolated PostgreSQL 16 instance and database names. Do not point these
commands at the MAX/mini-app database. Keep the generated database password in
this PowerShell session; it is unrelated to the Polza API key.

```powershell
$env:POSTGRES_PASSWORD = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(24))
docker run -d --name andromeda-bmstu-live-pg16 `
  -e POSTGRES_USER=andromeda -e POSTGRES_PASSWORD -e POSTGRES_DB=andromeda_core `
  -p 127.0.0.1:55432:5432 postgres:16-alpine
docker exec andromeda-bmstu-live-pg16 createdb -U andromeda andromeda_ingestion

$repoIngestion = (Get-Location).Path
$repoCore = Join-Path (Split-Path $repoIngestion -Parent) 'max_test'
$env:DATABASE_URL = 'postgresql+asyncpg://andromeda:{0}@127.0.0.1:55432/andromeda_core' -f $env:POSTGRES_PASSWORD
Push-Location $repoCore
python -m alembic upgrade head
$coreProcess = Start-Process -FilePath python -ArgumentList @('-m','uvicorn','andromeda_core.main:app','--host','127.0.0.1','--port','18100') -WorkingDirectory $repoCore -WindowStyle Hidden -PassThru
Pop-Location

$env:DATABASE_URL = 'postgresql+asyncpg://andromeda:{0}@127.0.0.1:55432/andromeda_ingestion' -f $env:POSTGRES_PASSWORD
$env:KNOWLEDGE_CORE_URL = 'http://127.0.0.1:18100'
$env:APP_ENV = 'development'
$env:MOCK_AI_ENABLED = 'false'
Push-Location $repoIngestion
alembic upgrade head
$ingestionProcess = Start-Process -FilePath python -ArgumentList @('-m','uvicorn','andromeda_ingestion.main:app','--host','127.0.0.1','--port','18101') -WorkingDirectory $repoIngestion -WindowStyle Hidden -PassThru
```

Wait until `http://127.0.0.1:18100/ready` and
`http://127.0.0.1:18101/ready` return successfully, then run:

```powershell
python scripts/live_bmstu_e2e.py --confirm-live-ai
```

The script also accepts `--core-url`, `--ingestion-url`, and `--report`. It
fails closed unless `.env` configures `AI_PROVIDER=polza`, the Polza endpoint,
`AI_MODEL=deepseek/deepseek-v4.1-flash`, `AI_TIMEOUT_SECONDS>=180`,
`AI_STRUCTURED_OUTPUT_MODE=json_object`, a non-empty `AI_API_KEY`, and
`MOCK_AI_ENABLED=false`. Never put a key in a command, document, report, or
source file.

The first run creates only a small curated ontology baseline through Core's
HTTP API if no active ontology exists. It does not call `scripts/seed_demo.py`,
create synthetic facts, accept observations, or activate rules. Rule candidates
must remain `DRAFT`/`NEEDS_REVIEW`; any `ACTIVE` result fails the evaluation.

## Safe ordinary tests

```powershell
pytest -q
ruff check .
mypy src scripts
```

The pytest fixture overrides provider settings and credentials, so local `.env`
cannot turn ordinary tests into paid live calls. To stop only this isolated
stack after inspection, use the saved process IDs in `$coreProcess` and
`$ingestionProcess`, then stop the specifically named container
`andromeda-bmstu-live-pg16` when its data is no longer needed.
