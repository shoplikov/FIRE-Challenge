from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.helpers import ticket_to_out
from app.database import get_session
from app.models.ticket import AIAnalysis, Assignment, Ticket
from app.schemas.ticket import TicketListOut, TicketOut

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


@router.get("", response_model=TicketListOut)
async def list_tickets(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    segment: str | None = None,
    category: str | None = None,
    sentiment: str | None = None,
    language: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    query = select(Ticket).options(
        selectinload(Ticket.ai_analysis),
        selectinload(Ticket.assignment).selectinload(Assignment.manager),
        selectinload(Ticket.assignment).selectinload(Assignment.business_unit),
    )

    count_query = select(func.count(Ticket.id))

    if segment:
        query = query.where(Ticket.segment == segment)
        count_query = count_query.where(Ticket.segment == segment)
    if category:
        query = query.join(AIAnalysis).where(AIAnalysis.category == category)
        count_query = count_query.join(AIAnalysis).where(AIAnalysis.category == category)
    if sentiment:
        if not category:
            query = query.join(AIAnalysis)
            count_query = count_query.join(AIAnalysis)
        query = query.where(AIAnalysis.sentiment == sentiment)
        count_query = count_query.where(AIAnalysis.sentiment == sentiment)
    if language:
        if not category and not sentiment:
            query = query.join(AIAnalysis)
            count_query = count_query.join(AIAnalysis)
        query = query.where(AIAnalysis.language == language)
        count_query = count_query.where(AIAnalysis.language == language)

    total = (await session.execute(count_query)).scalar() or 0
    query = query.offset((page - 1) * size).limit(size).order_by(Ticket.id)
    tickets = (await session.execute(query)).scalars().all()

    return TicketListOut(
        items=[ticket_to_out(t) for t in tickets],
        total=total,
    )


@router.get("/{ticket_id}", response_model=TicketOut)
async def get_ticket(
    ticket_id: int,
    session: AsyncSession = Depends(get_session),
):
    query = (
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .options(
            selectinload(Ticket.ai_analysis),
            selectinload(Ticket.assignment).selectinload(Assignment.manager),
            selectinload(Ticket.assignment).selectinload(Assignment.business_unit),
        )
    )
    ticket = (await session.execute(query)).scalar_one()
    return ticket_to_out(ticket)
