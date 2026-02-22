from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.business_unit import BusinessUnit
from app.models.ticket import AIAnalysis, Assignment, Ticket
from app.schemas.business_unit import BusinessUnitOut
from app.schemas.ticket import DashboardStats

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard/stats", response_model=DashboardStats)
async def dashboard_stats(session: AsyncSession = Depends(get_session)):
    total = (await session.execute(select(func.count(Ticket.id)))).scalar() or 0
    assigned = (await session.execute(select(func.count(Assignment.id)))).scalar() or 0
    avg_pri = (await session.execute(select(func.avg(AIAnalysis.priority)))).scalar() or 0.0

    cat_rows = (
        await session.execute(
            select(AIAnalysis.category, func.count()).group_by(AIAnalysis.category)
        )
    ).all()
    categories = {row[0]: row[1] for row in cat_rows}

    sent_rows = (
        await session.execute(
            select(AIAnalysis.sentiment, func.count()).group_by(AIAnalysis.sentiment)
        )
    ).all()
    sentiments = {row[0]: row[1] for row in sent_rows}

    lang_rows = (
        await session.execute(
            select(AIAnalysis.language, func.count()).group_by(AIAnalysis.language)
        )
    ).all()
    languages = {row[0]: row[1] for row in lang_rows}

    office_rows = (
        await session.execute(
            select(BusinessUnit.name, func.count(Assignment.id))
            .join(Assignment, Assignment.business_unit_id == BusinessUnit.id)
            .group_by(BusinessUnit.name)
        )
    ).all()
    offices_dist = {row[0]: row[1] for row in office_rows}

    seg_rows = (
        await session.execute(
            select(Ticket.segment, func.count()).group_by(Ticket.segment)
        )
    ).all()
    segments = {row[0]: row[1] for row in seg_rows}

    return DashboardStats(
        total_tickets=total,
        assigned_tickets=assigned,
        avg_priority=round(float(avg_pri), 2),
        categories=categories,
        sentiments=sentiments,
        languages=languages,
        offices=offices_dist,
        segments=segments,
    )


@router.get("/business-units", response_model=list[BusinessUnitOut])
async def list_business_units(session: AsyncSession = Depends(get_session)):
    result = (
        await session.execute(select(BusinessUnit).order_by(BusinessUnit.id))
    ).scalars().all()
    return [BusinessUnitOut.model_validate(bu) for bu in result]
