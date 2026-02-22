# Ticket Distribution Service

Automated ticket processing service for support operations:
- ingest CSV data (offices, managers, tickets),
- geocode office and ticket locations,
- classify tickets with LLM (category, sentiment, priority, language, summary),
- assign each ticket to the best manager by skills + load balancing,
- expose API + web dashboard.

## How It Works

### End-to-end pipeline
1. **Upload data** via `POST /api/upload` (3 CSV files + optional attachments).
2. **Geocoding** resolves office/ticket coordinates.
3. **NLP analysis** creates `AIAnalysis` records for each ticket.
4. **Assignment** picks office + manager:
   - primary office = nearest office (or Astana/Almaty split for unknown/foreign addresses),
   - manager eligibility filtered by skills/position/language,
   - if no eligible manager in primary office, fallback goes to the **closest office to that primary office** with eligible managers,
   - eligible managers are sorted by `current_load`, then round-robin among top two,
   - chosen manager load is incremented immediately so the next ticket uses updated load.
5. Results are available in dashboard/API tables.

### Main modules
- `app/api/upload.py`: full upload + process endpoint.
- `app/api/processing.py`: re-run pipeline on existing data.
- `app/api/tickets.py`: paginated and filterable tickets API.
- `app/api/managers.py`: managers list with current loads.
- `app/api/dashboard.py`: dashboard stats.
- `app/services/assignment.py`: assignment and fallback logic.
- `app/services/nlp.py`: LLM classification prompt/schema.
- `app/services/geocoding.py`: geocoding + distance helpers.

## Requirements

- Python `3.12+`
- Docker + Docker Compose (recommended path)
- OpenAI API key

## Environment Variables

Copy and edit:

```bash
cp .env.example .env
```

Important values:
- `OPENAI_API_KEY` (required for NLP analysis)
- `OPENAI_MODEL` (default `gpt-4o-mini`)
- `LANGFUSE_ENABLED` (set `true` to enable NLP tracing)
- `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`
- `LANGFUSE_BASE_URL` (default `https://cloud.langfuse.com`)
- `DATABASE_URL`
- `MINIO_ENDPOINT`
- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`
- `MINIO_BUCKET`
- `GEOCODER_USER_AGENT`

## Run with Docker Compose (Recommended)

From repo root:

```bash
docker compose up --build
```

This starts:
- `db` (PostgreSQL),
- `minio` (object storage),
- `migrate` (Alembic migrations),
- `app` (FastAPI service).

After startup:
- App: `http://localhost:8000`
- Swagger docs: `http://localhost:8000/docs`
- MinIO console: `http://localhost:9001` (default: `minioadmin` / `minioadmin`)

## Run Locally (Without Docker App Container)

You can still use Docker for dependencies (`db`, `minio`) and run app locally.

1) Start dependencies:

```bash
docker compose up -d db minio
```

2) Update `.env` for host networking:
- `DATABASE_URL=postgresql+asyncpg://tickets:tickets@localhost:5432/tickets_db`
- `MINIO_ENDPOINT=localhost:9000`

3) Install deps:

```bash
uv sync
```

4) Run migrations:

```bash
DATABASE_URL=postgresql+asyncpg://tickets:tickets@localhost:5432/tickets_db .venv/bin/alembic upgrade head
```

5) Start API:

```bash
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Basic Usage

### Web UI
- Open `http://localhost:8000`
- Upload:
  - `business_units.csv`
  - `managers.csv`
  - `tickets.csv`
  - optional attachments

Dashboard and manager table will update after processing.

### API
- `POST /api/upload` - upload CSVs and run full pipeline.
- `POST /api/process` - reprocess existing records.
- `GET /api/tickets` - list/filter tickets.
- `GET /api/managers` - manager list + current loads.
- `GET /api/dashboard/stats` - dashboard counters/charts data.

## Notes

- CSV uploads upsert by natural key (office name, manager name+office, ticket client GUID): existing rows are updated from the CSV, new rows are inserted, duplicates are skipped.
- Geocoding relies on Nominatim and is rate-limited.
- LLM classification quality depends on prompt/model and ticket text quality.
