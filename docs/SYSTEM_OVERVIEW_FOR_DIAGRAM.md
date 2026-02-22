# Ticket Distribution Service — Full Cycle & Logic (for Draw.io)

This document describes the end-to-end flow and logic of the project so you can create an accurate draw.io diagram.

---

## 1. System Purpose

**Ticket Auto-Distribution Service**: Ingest support tickets from CSV, geocode locations, classify with an LLM (category, sentiment, priority, language, summary), assign each ticket to the best manager by skills and load balancing, and expose results via API and web dashboard.

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EXTERNAL ACTORS                                     │
│  User (browser) / API client  →  POST /api/upload  or  GET /api/*            │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FASTAPI APP (app/main.py)                          │
│  Routers: upload, processing, tickets, managers, dashboard                   │
│  Static: / → app/static (index.html)                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
          ┌─────────────────────────────┼─────────────────────────────┐
          ▼                             ▼                             ▼
┌─────────────────┐         ┌─────────────────────┐       ┌─────────────────┐
│   SERVICES       │         │   DATABASE           │       │   EXTERNAL       │
│ csv_loader       │         │   PostgreSQL        │       │   MinIO          │
│ geocoding        │         │   (async SQLAlchemy)│       │   Nominatim      │
│ nlp              │         │   get_session()     │       │   OpenAI         │
│ assignment       │         │   (Alembic migrations)      │   Langfuse (opt)  │
│ minio_client     │         │                     │       │                  │
└─────────────────┘         └─────────────────────┘       └─────────────────┘
```

---

## 3. Data Model (Entity Relationship)

Use this for the **database/entity diagram** in draw.io.

| Entity         | Table           | Key fields | Relationships |
|----------------|-----------------|------------|---------------|
| **BusinessUnit** | business_units | id, name (unique), address, latitude, longitude | 1 → N Manager, 1 → N Assignment |
| **Manager**      | managers       | id, name, position, skills[], business_unit_id, current_load | N → 1 BusinessUnit, 1 → N Assignment |
| **Ticket**       | tickets        | id, client_guid (natural key for upsert), description, segment, country/region/city/street/house, latitude/longitude, attachment_key, created_at | 1 → 0..1 AIAnalysis, 1 → 0..1 Assignment |
| **AIAnalysis**    | ai_analyses    | id, ticket_id (unique), category, sentiment, priority, language, summary | 1 → 1 Ticket, 0..1 → 1 Assignment |
| **Assignment**    | assignments   | id, ticket_id (unique), ai_analysis_id, manager_id, business_unit_id, assigned_at, reason | 1 → 1 Ticket, 1 → 1 AIAnalysis, N → 1 Manager, N → 1 BusinessUnit |

**Cascade**: Deleting a Ticket deletes its AIAnalysis and Assignment. Deleting Manager/BusinessUnit cascades to Assignment.

**Natural keys for CSV upsert**:
- BusinessUnit: by **name** (office name)
- Manager: by **(name, business_unit_id)** i.e. (name, office)
- Ticket: by **client_guid**

---

## 4. API Endpoints (for Draw.io “API layer” swimlane)

| Method | Path | Purpose |
|--------|------|---------|
| POST | /api/upload | Upload 3 CSVs + optional attachments → run **full pipeline** (ingest, geocode, NLP, assignment). Returns PipelineResult. |
| POST | /api/process | Re-run **geocode + NLP + assignment** on existing DB data (no CSV upload). Returns PipelineResult. |
| GET | /api/tickets | Paginated list; filters: segment, category, sentiment, language. Returns TicketListOut. |
| GET | /api/tickets/{id} | Single ticket with AI analysis and assignment. Returns TicketOut. |
| GET | /api/managers | All managers with business_unit name and current_load. |
| GET | /api/dashboard/stats | Aggregated stats: total/assigned tickets, avg priority, counts by category/sentiment/language/office/segment. |
| GET | /api/business-units | List all business units. |
| GET | / | Static web UI (index.html). |

---

## 5. Full Pipeline Cycle (POST /api/upload)

This is the **main flow** to draw as a sequence or flowchart.

### Step 1 — Ingest CSVs (csv_loader)

- **Input**: 3 files — business_units.csv, managers.csv, tickets.csv (in-memory StringIO after decode).
- **load_business_units(session, file)**  
  - Reads CSV columns: Офис, Адрес.  
  - Upsert by **office name**: existing row → update address (and clear lat/lon if address changed); new → insert.  
  - Returns `dict[name → BusinessUnit]` (bu_map).
- **load_managers(session, bu_map, file)**  
  - Columns: ФИО, Должность, Навыки (comma-separated), Офис, Количество обращений в работе.  
  - Resolve office name → BusinessUnit via bu_map.  
  - Upsert by (name, business_unit_id): update position/skills/current_load or insert.  
  - Returns list of Manager.
- **load_tickets(session, file)**  
  - Columns: GUID клиента, Пол, Дата рождения, Описание, Вложения, Сегмент, Страна, Область, Населённый пункт, Улица, Дом.  
  - Upsert by **client_guid**: if exists → update all fields and **delete** existing AIAnalysis and Assignment for that ticket; else insert new Ticket.  
  - Returns list of Ticket.
- **Commit** after all three.

### Step 2 — Attachments to MinIO (minio_client)

- For each uploaded attachment file: `upload_file_bytes(filename, data, content_type)`.
- Ensures bucket exists, then `put_object`. Attachment keys are stored in Ticket.attachment_key (from CSV “Вложения” or from upload; upload in this flow does not auto-link to tickets — typically CSV carries the key).
- Errors collected in `errors[]`, not failing the request.

### Step 3 — Geocoding (geocoding)

- **geocode_business_units(session, offices)**  
  - For each BusinessUnit with latitude is NULL: build address strings (e.g. address + name + "Казахстан"), call Nominatim (rate-limited 1 req/s), write lat/lon.  
- **geocode_tickets(session, tickets)**  
  - For each Ticket with latitude NULL and city set: build address from country/region, call Nominatim, write lat/lon.  
- **Commit**.

### Step 4 — AI analysis (nlp)

- Load all tickets with `ai_analysis` and `assignment` eager-loaded.
- **analyze_all_tickets(session, tickets)**  
  - Filter to tickets where `ai_analysis is None`.  
  - For each: call **analyze_ticket(description)** → OpenAI (ChatOpenAI) with structured output `TicketAnalysis` (category, sentiment, priority, language, summary).  
  - Concurrency limited by semaphore (5). Optional Langfuse tracing.  
  - Create AIAnalysis row per ticket, add to session.  
- **Commit**.

### Step 5 — Assignment (assignment)

- Load all AIAnalysis, all Manager, all BusinessUnit; reload tickets with relations.
- **assign_tickets(session, tickets, analyses, managers, offices)**  
  - Build analysis_map (ticket_id → AIAnalysis), office maps, managers_by_office.  
  - Sort (ticket, analysis) by **priority descending**.  
  - For each ticket that has no assignment yet:  
    1. **Office selection**  
       - If ticket is “foreign/unknown” (no coords or country ≠ Казахстан): alternate 50/50 between Astana and Almaty offices.  
       - Else: **find_nearest_office(ticket.lat, ticket.lon, offices)** (geodesic distance).  
    2. **Eligible managers** in that office: filter by skills (VIP for VIP/Priority segment; “Главный специалист” for category “Смена данных”; language KZ/ENG must be in manager skills).  
    3. **Fallback**: if no eligible manager in primary office, iterate other offices by **distance from primary office**, take first office that has eligible managers; set target_office to that fallback, add reason.  
    4. **Choose manager**: among eligible, sort by current_load; take top 2; **round-robin** between these two (per office); create Assignment, **increment chosen manager’s current_load** immediately.  
  - Flush to DB.  
- **Commit**.

### Step 6 — Response

- Reload tickets with assignment.manager and assignment.business_unit.
- Build **PipelineResult**: tickets_loaded, tickets_analyzed, tickets_assigned, errors, tickets (each via **ticket_to_out**: adds attachment_url from MinIO presigned URL, manager_name, business_unit_name).

---

## 6. Re-Process Pipeline (POST /api/process)

- No file upload.  
- If no BusinessUnits or no Managers → return error in PipelineResult.  
- **Same steps 3–6** as above: geocode offices → geocode tickets → commit → analyze_all_tickets → commit → assign_tickets → commit → build PipelineResult from DB.  
- Use this flow in draw.io as a “variant” of the main pipeline without CSV ingest and without MinIO upload.

---

## 7. Read-Only APIs (for Diagram)

- **GET /api/tickets**: Filter by segment/category/sentiment/language; paginate (page, size); return TicketListOut (items + total). Each item via ticket_to_out (presigned attachment_url, assignment names).  
- **GET /api/tickets/{id}**: Single ticket by id, same TicketOut.  
- **GET /api/managers**: All managers with business_unit loaded; ManagerOut (id, name, position, skills, business_unit_id, business_unit_name, current_load).  
- **GET /api/dashboard/stats**: Counts and aggregates from Ticket, Assignment, AIAnalysis, BusinessUnit, grouped by category, sentiment, language, office (assignments per office), segment.  
- **GET /api/business-units**: List BusinessUnit.

---

## 8. External Systems (Draw.io: external entities)

| System    | Role |
|-----------|------|
| **PostgreSQL** | Persistent store for BusinessUnit, Manager, Ticket, AIAnalysis, Assignment. |
| **MinIO**      | Object storage for attachment files; presigned URLs for download. |
| **Nominatim**  | Geocoding (address → lat/lon); rate limit 1 req/s. |
| **OpenAI**     | LLM for ticket classification (category, sentiment, priority, language, summary). |
| **Langfuse**   | Optional tracing for LLM calls (env: LANGFUSE_*). |

---

## 9. Suggested Draw.io Diagram Structure

1. **Context diagram**: User / API client ↔ FastAPI app ↔ PostgreSQL, MinIO, Nominatim, OpenAI.  
2. **Pipeline flowchart**:  
   Upload → Ingest (3 CSVs) → MinIO attachments → Geocode offices → Geocode tickets → NLP (OpenAI) → Assignment (nearest office / fallback / round-robin) → Response.  
   Optionally a second path: “Re-process” starting at Geocode (no CSV).  
3. **Data model**: Five entities (BusinessUnit, Manager, Ticket, AIAnalysis, Assignment) with relationships and cardinality.  
4. **Assignment logic (optional sub-diagram)**:  
   Ticket + AIAnalysis → foreign/unknown? → Astana/Almaty 50/50 **or** nearest office → filter managers by skills → no one? → fallback by distance to other offices → sort by load → top 2 → round-robin → create Assignment, increment load.

---

## 10. File-to-Component Mapping (for Draw.io “components”)

| Component / Logic | File(s) |
|-------------------|--------|
| App entry, routes | app/main.py |
| Upload + full pipeline | app/api/upload.py |
| Re-process pipeline | app/api/processing.py |
| Ticket list/detail | app/api/tickets.py |
| Managers list | app/api/managers.py |
| Dashboard + business-units | app/api/dashboard.py |
| Ticket → API shape, presigned URL | app/api/helpers.py |
| CSV ingest | app/services/csv_loader.py |
| Geocoding + nearest office | app/services/geocoding.py |
| LLM analysis | app/services/nlp.py |
| Assignment + fallback + round-robin | app/services/assignment.py |
| MinIO upload + presigned URL | app/services/minio_client.py |
| DB session | app/database.py |
| Models | app/models/*.py |
| Schemas | app/schemas/*.py |
| Migrations | alembic/versions/001_initial_schema.py |

You can now map these flows and entities directly into draw.io (swimlanes for API / Services / DB / External, and shapes for entities and steps).
