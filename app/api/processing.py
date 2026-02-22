import logging

from fastapi import APIRouter, Depends
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
from app.services.geocoding import geocode_business_units, geocode_tickets
from app.services.nlp import analyze_all_tickets

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["processing"])


@router.post("/process", response_model=PipelineResult)
async def run_pipeline(session: AsyncSession = Depends(get_session)):
    """Re-run AI analysis, geocoding, and assignment on already-uploaded data.

    Use POST /api/upload to upload CSVs and run the full pipeline in one step.
    This endpoint is for re-processing existing data.
    """
    errors: list[str] = []

    all_offices = list((await session.execute(select(BusinessUnit))).scalars().all())
    all_managers = list((await session.execute(select(Manager))).scalars().all())

    if not all_offices or not all_managers:
        errors.append("No data loaded yet. Upload CSVs first via POST /api/upload.")
        return PipelineResult(
            tickets_loaded=0, tickets_analyzed=0, tickets_assigned=0,
            errors=errors, tickets=[],
        )

    await geocode_business_units(session, all_offices)

    tickets = list(
        (await session.execute(
            select(Ticket).options(
                selectinload(Ticket.ai_analysis),
                selectinload(Ticket.assignment),
            )
        )).scalars().all()
    )

    await geocode_tickets(session, tickets)
    await session.commit()

    new_analyses = await analyze_all_tickets(session, tickets)
    await session.commit()

    all_analyses = list((await session.execute(select(AIAnalysis))).scalars().all())
    all_managers = list((await session.execute(select(Manager))).scalars().all())
    all_offices = list((await session.execute(select(BusinessUnit))).scalars().all())

    tickets = list(
        (await session.execute(
            select(Ticket).options(
                selectinload(Ticket.ai_analysis),
                selectinload(Ticket.assignment),
            )
        )).scalars().all()
    )

    assignments = await assign_tickets(session, tickets, all_analyses, all_managers, all_offices)
    await session.commit()

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
