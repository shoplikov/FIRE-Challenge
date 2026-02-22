# Ticket Distribution Service

FastAPI app that loads office, manager and ticket CSVs, geocodes addresses, runs LLM analysis on ticket text, and assigns each ticket to a manager (nearest office + skills + load balancing). Data is stored in PostgreSQL; attachments go to MinIO. A static web UI and REST API expose the data.

## Pipeline (POST /api/upload)

1. **CSV load** — Business units, managers, tickets. Upsert by office name, (manager name + office), and ticket client GUID. Existing tickets get their AI analysis and assignment deleted before re-processing.
2. **Geocoding** — Nominatim geocodes business unit addresses and ticket locations (country, region, city). Results stored on `BusinessUnit` and `Ticket`. Rate-limited (1 req/s).
3. **AI analysis** — For each ticket without an analysis, the LLM gets the ticket description and returns category, sentiment, priority, language, summary. Stored in `ai_analyses`.
4. **Assignment** — For each (ticket, analysis):
   - **Office**: nearest office by coordinates, or 50/50 Astana/Almaty for unknown/foreign.
   - **Managers**: restricted to that office, then filtered by skills (VIP segment → "VIP" in skills; category "Смена данных" → position "Главный специалист"; language KZ/ENG → language in skills). If none, fallback to next nearest office with eligible managers.
   - **Choice**: sort eligible by `current_load`, take top 2, round-robin between them; increment chosen manager’s load.
5. **Attachments** — Uploaded to MinIO; ticket `attachment_key` is the filename.

## Data model

- **business_units** — name, address, latitude, longitude
- **managers** — name, position, skills (array), business_unit_id, current_load
- **tickets** — client_guid, description, segment, address fields (country, region, city, street, house), latitude, longitude, attachment_key, etc.
- **ai_analyses** — ticket_id, category, sentiment, priority, language, summary
- **assignments** — ticket_id, ai_analysis_id, manager_id, business_unit_id, reason, assigned_at

## CSV format

- **business_units**: `Офис`, `Адрес`
- **managers**: `ФИО`, `Должность`, `Навыки` (comma-separated), `Офис`, `Количество обращений в работе`
- **tickets**: `GUID клиента`, `Описание`, `Сегмент клиента`, `Вложения`, plus optional `Пол клиента`, `Дата рождения`, `Страна`, `Область`, `Населённый пункт`, `Улица`, `Дом`. Date formats: `%Y-%m-%d %H:%M`, `%Y-%m-%d %H:%M:%S`, `%Y-%m-%d`

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/upload` | Upload business_units, managers, tickets CSVs + optional attachments; run full pipeline |
| POST | `/api/process` | Re-run geocoding, AI analysis, and assignment on existing data |
| GET | `/api/tickets` | List tickets, paginated; filter by segment, category, sentiment, language |
| GET | `/api/tickets/export` | Export tickets as CSV |
| GET | `/api/tickets/{ticket_id}` | Single ticket with analysis and assignment |
| GET | `/api/managers` | All managers with current_load |
| GET | `/api/dashboard/stats` | Counts and aggregates (tickets, assigned, categories, sentiments, languages, offices, segments) |
| GET | `/api/business-units` | All business units |
| GET | `/api/dashboard/map` | Business units with lat/lon (for map) |
| GET | `/api/dashboard/business-units/{unit_id}/managers` | Managers of one business unit with assignment count |
| POST | `/api/dashboard/ai-chart` | Body: `{ "query": "..." }`. Parses natural-language chart request, returns chart_type + data_1d/data_2d |

Static UI: `/` (Single-page app in `app/static`).

## Project layout

- `app/main.py` — FastAPI app, mounts API routers and static files
- `app/api/upload.py` — upload + pipeline
- `app/api/processing.py` — re-run pipeline
- `app/api/tickets.py` — tickets list, export, detail
- `app/api/managers.py` — managers list
- `app/api/dashboard.py` — stats, business-units, map, ai-chart, business-unit managers
- `app/services/csv_loader.py` — load/upsert from CSVs
- `app/services/geocoding.py` — Nominatim geocoding, `find_nearest_office`, `get_distance_km`
- `app/services/nlp.py` — LLM analysis (OpenAI, structured output: category, sentiment, priority, language, summary)
- `app/services/assignment.py` — office selection, skill filter, round-robin assignment
- `app/services/minio_client.py` — upload attachment bytes to MinIO
- `app/services/chart_aggregation.py` — build chart data for dashboard
- `app/services/chart_intent.py` — parse natural-language chart query (LLM)
- `app/models/` — SQLAlchemy models (BusinessUnit, Manager, Ticket, AIAnalysis, Assignment)
- `app/schemas/` — Pydantic request/response schemas
- `alembic/` — migrations (PostgreSQL)

## Config (env)

From `.env` (see `.env.example`):

- `DATABASE_URL` — PostgreSQL (async driver, e.g. `postgresql+asyncpg://...`)
- `OPENAI_API_KEY`, `OPENAI_MODEL` (default `gpt-4o-mini`) — for NLP and chart intent
- `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET` — object storage
- `GEOCODER_USER_AGENT` — for Nominatim
- `LANGFUSE_*` — optional tracing (langfuse_enabled, public/secret key, base_url)

## Run

**Docker Compose** (from repo root):

```bash
docker compose up --build
```

Runs: PostgreSQL (`db`), MinIO (`minio`), Alembic migrate, FastAPI app. App at `http://localhost:8000`, docs at `http://localhost:8000/docs`, MinIO console at `http://localhost:9001`.

**Local app, Docker deps only:**

```bash
docker compose up -d db minio
# Set DATABASE_URL and MINIO_ENDPOINT for localhost (e.g. localhost:5432, localhost:9000)
uv sync
# DATABASE_URL=... alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Requirements

- Python 3.12+
- PostgreSQL, MinIO (or compatible S3)
- OpenAI API key for LLM analysis and dashboard AI chart
