import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
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


def _ticket_row(t) -> list[str]:
    """One ticket as CSV row: guid, manager_name, category, priority, language, summary, assigned_at."""
    out = ticket_to_out(t)
    return [
        str(out.client_guid),
        out.assignment.manager_name if out.assignment else "",
        out.ai_analysis.category if out.ai_analysis else "",
        str(out.ai_analysis.priority) if out.ai_analysis else "",
        out.ai_analysis.language if out.ai_analysis else "",
        (out.ai_analysis.summary or "").replace("\n", " ").replace("\r", "") if out.ai_analysis else "",
        out.assignment.assigned_at.isoformat() if out.assignment and out.assignment.assigned_at else "",
    ]


CSV_HEADER = ["guid", "manager_name", "category", "priority", "language", "summary", "assigned_at"]


@router.get("/export", response_class=StreamingResponse)
async def export_tickets_csv(
    segment: str | None = None,
    category: str | None = None,
    sentiment: str | None = None,
    language: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Export all tickets (with current filters) as CSV download."""
    query = select(Ticket).options(
        selectinload(Ticket.ai_analysis),
        selectinload(Ticket.assignment).selectinload(Assignment.manager),
        selectinload(Ticket.assignment).selectinload(Assignment.business_unit),
    ).order_by(Ticket.id)
    if segment:
        query = query.where(Ticket.segment == segment)
    if category:
        query = query.join(AIAnalysis).where(AIAnalysis.category == category)
    if sentiment:
        if not category:
            query = query.join(AIAnalysis)
        query = query.where(AIAnalysis.sentiment == sentiment)
    if language:
        if not category and not sentiment:
            query = query.join(AIAnalysis)
        query = query.where(AIAnalysis.language == language)
    tickets = (await session.execute(query)).scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_HEADER)
    for t in tickets:
        writer.writerow(_ticket_row(t))
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tickets.csv"},
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
