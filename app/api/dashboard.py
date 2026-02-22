from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.business_unit import BusinessUnit
from app.models.ticket import AIAnalysis, Assignment, Ticket
from app.schemas.business_unit import BusinessUnitOut
from app.schemas.ticket import (
    AIChartRequest,
    AIChartResponse,
    DashboardStats,
)
from app.services.chart_aggregation import get_chart_data
from app.services.chart_intent import parse_chart_query

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


@router.post("/dashboard/ai-chart", response_model=AIChartResponse)
async def ai_chart(
    body: AIChartRequest,
    session: AsyncSession = Depends(get_session),
):
    """Parse natural-language query and return chart data (1D or 2D)."""
    try:
        intent = await parse_chart_query(body.query)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail="Не удалось определить параметры графика. Уточните запрос.",
        ) from e

    try:
        data_1d, data_2d = await get_chart_data(session, intent)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    title = intent.title or "График"
    return AIChartResponse(
        title=title,
        chart_type=intent.chart_type,
        data_1d=data_1d,
        data_2d=data_2d,
    )
