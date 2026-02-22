import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_unit import BusinessUnit
from app.models.manager import Manager
from app.models.ticket import AIAnalysis, Assignment, Ticket
from app.services.geocoding import find_nearest_office

logger = logging.getLogger(__name__)

ASTANA = "Астана"
ALMATY = "Алматы"
KAZAKHSTAN = "Казахстан"


def _is_foreign_or_unknown(ticket: Ticket) -> bool:
    if ticket.latitude is None or ticket.longitude is None:
        return True
    if ticket.country and ticket.country.strip().lower() != "казахстан":
        return True
    return False


def _filter_by_skills(
    managers: list[Manager],
    ticket: Ticket,
    analysis: AIAnalysis,
) -> list[Manager]:
    eligible = list(managers)

    if ticket.segment in ("VIP", "Priority"):
        eligible = [m for m in eligible if "VIP" in m.skills]

    if analysis.category == "Смена данных":
        eligible = [m for m in eligible if m.position == "Главный специалист"]

    if analysis.language in ("KZ", "ENG"):
        eligible = [m for m in eligible if analysis.language in m.skills]

    return eligible


class RoundRobinState:
    """Tracks which manager was last assigned within each (office, pair) group."""

    def __init__(self) -> None:
        self._counters: dict[tuple[int, ...], int] = {}

    def next(self, office_id: int, manager_ids: tuple[int, ...]) -> int:
        key = (office_id, *manager_ids)
        idx = self._counters.get(key, -1)
        idx = (idx + 1) % len(manager_ids)
        self._counters[key] = idx
        return manager_ids[idx]


async def assign_tickets(
    session: AsyncSession,
    tickets: list[Ticket],
    analyses: list[AIAnalysis],
    managers: list[Manager],
    offices: list[BusinessUnit],
) -> list[Assignment]:
    analysis_map: dict[int, AIAnalysis] = {a.ticket_id: a for a in analyses}
    office_map: dict[int, BusinessUnit] = {bu.id: bu for bu in offices}
    office_name_map: dict[str, BusinessUnit] = {bu.name: bu for bu in offices}
    managers_by_office: dict[int, list[Manager]] = {}
    for m in managers:
        managers_by_office.setdefault(m.business_unit_id, []).append(m)

    astana = office_name_map.get(ASTANA)
    almaty = office_name_map.get(ALMATY)
    foreign_toggle = 0  # 0 = Астана, 1 = Алматы for 50/50 split

    sortable = []
    for t in tickets:
        a = analysis_map.get(t.id)
        if a:
            sortable.append((t, a))
    sortable.sort(key=lambda x: x[1].priority, reverse=True)

    rr = RoundRobinState()
    assignments: list[Assignment] = []
    errors: list[str] = []

    for ticket, analysis in sortable:
        if ticket.assignment is not None:
            continue

        target_office: BusinessUnit | None = None
        reason_parts: list[str] = []

        if _is_foreign_or_unknown(ticket):
            if foreign_toggle == 0 and astana:
                target_office = astana
                reason_parts.append("Адрес неизвестен/зарубежный → распределение в Астану (50/50)")
            elif almaty:
                target_office = almaty
                reason_parts.append("Адрес неизвестен/зарубежный → распределение в Алматы (50/50)")
            foreign_toggle = 1 - foreign_toggle
        else:
            target_office = find_nearest_office(ticket.latitude, ticket.longitude, offices)
            if target_office:
                reason_parts.append(f"Ближайший офис: {target_office.name}")

        if target_office is None:
            errors.append(f"Ticket {ticket.id}: no target office found")
            logger.warning("No target office for ticket %d", ticket.id)
            continue

        office_managers = managers_by_office.get(target_office.id, [])
        eligible = _filter_by_skills(office_managers, ticket, analysis)

        if not eligible:
            other_offices = sorted(
                [bu for bu in offices if bu.id != target_office.id and bu.latitude is not None],
                key=lambda bu: (
                    ((ticket.latitude or 0) - (bu.latitude or 0)) ** 2
                    + ((ticket.longitude or 0) - (bu.longitude or 0)) ** 2
                ),
            )
            for fallback_office in other_offices:
                fallback_managers = managers_by_office.get(fallback_office.id, [])
                eligible = _filter_by_skills(fallback_managers, ticket, analysis)
                if eligible:
                    target_office = fallback_office
                    reason_parts.append(f"Фоллбэк на офис {fallback_office.name} (нет подходящих менеджеров в первичном)")
                    break

        if not eligible:
            errors.append(f"Ticket {ticket.id}: no eligible managers")
            logger.warning("No eligible managers for ticket %d", ticket.id)
            continue

        eligible.sort(key=lambda m: m.current_load)
        top_two = eligible[:2]
        top_ids = tuple(m.id for m in top_two)

        chosen_id = rr.next(target_office.id, top_ids)
        chosen = next(m for m in top_two if m.id == chosen_id)

        skill_info = []
        if ticket.segment in ("VIP", "Priority"):
            skill_info.append("VIP-навык")
        if analysis.category == "Смена данных":
            skill_info.append("Главный специалист")
        if analysis.language in ("KZ", "ENG"):
            skill_info.append(f"навык {analysis.language}")
        if skill_info:
            reason_parts.append(f"Фильтр компетенций: {', '.join(skill_info)}")

        reason_parts.append(f"Round Robin → {chosen.name} (нагрузка: {chosen.current_load})")

        assignment = Assignment(
            ticket_id=ticket.id,
            ai_analysis_id=analysis.id,
            manager_id=chosen.id,
            business_unit_id=target_office.id,
            reason=" | ".join(reason_parts),
        )
        session.add(assignment)
        chosen.current_load += 1
        assignments.append(assignment)

    await session.flush()
    logger.info("Assigned %d tickets, %d errors", len(assignments), len(errors))
    return assignments
