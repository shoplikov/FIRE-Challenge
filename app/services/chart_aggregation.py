from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_unit import BusinessUnit
from app.models.ticket import AIAnalysis, Assignment, Ticket
from app.schemas.ticket import ChartData2D, ChartSeries

from .chart_intent import ChartIntent

ALLOWED_DIMENSIONS = frozenset(
    {"city", "region", "country", "category", "sentiment", "language", "segment", "office"}
)

NULL_LABEL = "—"
NULL_OFFICE_LABEL = "Не назначен"


def _dimension_column(dim: str):
    """Return the expression to group by for dimension name."""
    if dim == "city":
        return func.coalesce(Ticket.city, NULL_LABEL)
    if dim == "region":
        return func.coalesce(Ticket.region, NULL_LABEL)
    if dim == "country":
        return func.coalesce(Ticket.country, NULL_LABEL)
    if dim == "segment":
        return Ticket.segment
    if dim == "category":
        return func.coalesce(AIAnalysis.category, NULL_LABEL)
    if dim == "sentiment":
        return func.coalesce(AIAnalysis.sentiment, NULL_LABEL)
    if dim == "language":
        return func.coalesce(AIAnalysis.language, NULL_LABEL)
    if dim == "office":
        return func.coalesce(BusinessUnit.name, NULL_OFFICE_LABEL)
    raise ValueError(f"Unknown dimension: {dim}")


async def get_chart_data(
    session: AsyncSession, intent: ChartIntent
) -> tuple[dict[str, int] | None, ChartData2D | None]:
    """
    Run aggregation from ChartIntent. Returns (data_1d, data_2d); exactly one is set.
    """
    group_by = intent.group_by
    breakdown_by = intent.breakdown_by

    if group_by not in ALLOWED_DIMENSIONS:
        raise ValueError(f"Invalid group_by: {group_by}")
    if breakdown_by is not None and breakdown_by not in ALLOWED_DIMENSIONS:
        raise ValueError(f"Invalid breakdown_by: {breakdown_by}")

    col1 = _dimension_column(group_by)

    if breakdown_by is None:
        # 1D: group by single dimension
        stmt = (
            select(col1, func.count(Ticket.id))
            .select_from(Ticket)
            .outerjoin(AIAnalysis, Ticket.id == AIAnalysis.ticket_id)
            .outerjoin(Assignment, Ticket.id == Assignment.ticket_id)
            .outerjoin(BusinessUnit, Assignment.business_unit_id == BusinessUnit.id)
            .group_by(col1)
        )
        rows = (await session.execute(stmt)).all()
        data_1d = {str(row[0]): row[1] for row in rows}
        return (data_1d, None)

    # 2D: group by both dimensions -> labels (dim1) and series (dim2 values with counts per label)
    col2 = _dimension_column(breakdown_by)
    stmt = (
        select(col1, col2, func.count(Ticket.id))
        .select_from(Ticket)
        .outerjoin(AIAnalysis, Ticket.id == AIAnalysis.ticket_id)
        .outerjoin(Assignment, Ticket.id == Assignment.ticket_id)
        .outerjoin(BusinessUnit, Assignment.business_unit_id == BusinessUnit.id)
        .group_by(col1, col2)
    )
    rows = (await session.execute(stmt)).all()

    # Build ordered labels (unique dim1 values), then for each dim2 value a series
    labels_list: list[str] = []
    seen_labels: set[str] = set()
    dim2_values: list[str] = []
    seen_dim2: set[str] = set()
    # (label_idx, dim2_value) -> count
    count_map: dict[tuple[int, str], int] = {}

    for r in rows:
        l1, l2, cnt = str(r[0]), str(r[1]), r[2]
        if l1 not in seen_labels:
            seen_labels.add(l1)
            labels_list.append(l1)
        if l2 not in seen_dim2:
            seen_dim2.add(l2)
            dim2_values.append(l2)
        idx = labels_list.index(l1)
        count_map[(idx, l2)] = cnt

    # Series: one per dim2 value, each with len(labels_list) values
    series_list = []
    for d2 in dim2_values:
        values = [count_map.get((i, d2), 0) for i in range(len(labels_list))]
        series_list.append(ChartSeries(name=d2, values=values))

    data_2d = ChartData2D(labels=labels_list, series=series_list)
    return (None, data_2d)
