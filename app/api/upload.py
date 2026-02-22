import io
import logging

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.helpers import ticket_to_out
from app.database import get_session
from app.models.business_unit import BusinessUnit
from app.models.manager import Manager
from app.models.ticket import AIAnalysis, Assignment, Ticket
from app.schemas.ticket import PipelineResult
from app.services.assignment import assign_tickets
from app.services.csv_loader import load_business_units, load_managers, load_tickets
from app.services.geocoding import geocode_business_units, geocode_tickets
from app.services.minio_client import upload_file_bytes
from app.services.nlp import analyze_all_tickets

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["upload"])


async def _read_csv_upload(file: UploadFile) -> io.StringIO:
    raw = await file.read()
    text = raw.decode("utf-8")
    return io.StringIO(text)


@router.post("/upload", response_model=PipelineResult)
async def upload_and_process(
    business_units_csv: UploadFile = File(..., description="business_units.csv"),
    managers_csv: UploadFile = File(..., description="managers.csv"),
    tickets_csv: UploadFile = File(..., description="tickets.csv"),
    attachments: list[UploadFile] = File(default=[], description="Attachment files (images, etc.)"),
    session: AsyncSession = Depends(get_session),
):
    """Upload CSVs + attachments, then run the full pipeline (geocoding, AI analysis, assignment) in one call.

    Returns every ticket with its AI analysis and assigned manager.
    """
    errors: list[str] = []

    # --- 1. Ingest CSVs ---
    bu_file = await _read_csv_upload(business_units_csv)
    mgr_file = await _read_csv_upload(managers_csv)
    tkt_file = await _read_csv_upload(tickets_csv)

    bu_map = await load_business_units(session, file=bu_file)
    managers = await load_managers(session, bu_map, file=mgr_file)
    tickets = await load_tickets(session, file=tkt_file)
    await session.commit()

    # --- 2. Upload attachments to MinIO ---
    for att in attachments:
        if att.filename:
            try:
                data = await att.read()
                upload_file_bytes(att.filename, data, att.content_type or "application/octet-stream")
            except Exception as e:
                errors.append(f"Attachment '{att.filename}': {e}")

    # --- 3. Geocode ---
    offices = list(bu_map.values())
    await geocode_business_units(session, offices)
    await geocode_tickets(session, tickets)
    await session.commit()

    # --- 4. AI analysis ---
    tickets_with_rel = list(
        (await session.execute(
            select(Ticket).options(
                selectinload(Ticket.ai_analysis),
                selectinload(Ticket.assignment),
            )
        )).scalars().all()
    )
    new_analyses = await analyze_all_tickets(session, tickets_with_rel)
    await session.commit()

    # --- 5. Assignment ---
    all_analyses = list((await session.execute(select(AIAnalysis))).scalars().all())
    all_managers = list((await session.execute(select(Manager))).scalars().all())
    all_offices = list((await session.execute(select(BusinessUnit))).scalars().all())

    tickets_with_rel = list(
        (await session.execute(
            select(Ticket).options(
                selectinload(Ticket.ai_analysis),
                selectinload(Ticket.assignment),
            )
        )).scalars().all()
    )
    assignments = await assign_tickets(session, tickets_with_rel, all_analyses, all_managers, all_offices)
    await session.commit()

    # --- 6. Build full output ---
    final_tickets = list(
        (await session.execute(
            select(Ticket).options(
                selectinload(Ticket.ai_analysis),
                selectinload(Ticket.assignment).selectinload(Assignment.manager),
                selectinload(Ticket.assignment).selectinload(Assignment.business_unit),
            ).order_by(Ticket.id)
        )).scalars().all()
    )

    return PipelineResult(
        tickets_loaded=len(tickets),
        tickets_analyzed=len(new_analyses),
        tickets_assigned=len(assignments),
        errors=errors,
        tickets=[ticket_to_out(t) for t in final_tickets],
    )
