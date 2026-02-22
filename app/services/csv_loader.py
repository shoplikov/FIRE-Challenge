import csv
import io
import logging
import uuid
from datetime import date, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_unit import BusinessUnit
from app.models.manager import Manager
from app.models.ticket import AIAnalysis, Assignment, Ticket

logger = logging.getLogger(__name__)

POSITION_MAP = {
    "Специалист": "Специалист",
    "Ведущий специалист": "Ведущий специалист",
    "Главный специалист": "Главный специалист",
}


def _clean_row(row: dict[str, str]) -> dict[str, str]:
    """Strip whitespace and BOM from both keys and values."""
    return {
        k.strip().lstrip("\ufeff"): (v.strip() if v else "")
        for k, v in row.items()
    }


def _make_reader(file: io.StringIO) -> csv.DictReader:
    """Build a DictReader from in-memory CSV content."""
    content = file.getvalue().lstrip("\ufeff")
    return csv.DictReader(io.StringIO(content))


async def load_business_units(
    session: AsyncSession, file: io.StringIO
) -> dict[str, BusinessUnit]:
    existing_list = (await session.execute(select(BusinessUnit))).scalars().all()
    result: dict[str, BusinessUnit] = {bu.name: bu for bu in existing_list}

    reader = _make_reader(file)
    for raw_row in reader:
        row = _clean_row(raw_row)
        name = row["Офис"]
        address = row["Адрес"]
        if name in result:
            bu = result[name]
            if bu.address != address:
                bu.latitude = None
                bu.longitude = None
            bu.address = address
        else:
            bu = BusinessUnit(name=name, address=address)
            session.add(bu)
            result[name] = bu

    await session.flush()
    logger.info("Loaded %d business units (upsert)", len(result))
    return result


def _manager_key(m: Manager) -> tuple[str, int]:
    return (m.name, m.business_unit_id)


async def load_managers(
    session: AsyncSession,
    bu_map: dict[str, BusinessUnit],
    file: io.StringIO,
) -> list[Manager]:
    existing_list = (await session.execute(select(Manager))).scalars().all()
    by_key: dict[tuple[str, int], Manager] = {_manager_key(m): m for m in existing_list}

    reader = _make_reader(file)
    managers: list[Manager] = list(existing_list)
    for raw_row in reader:
        row = _clean_row(raw_row)
        name = row["ФИО"]
        position = POSITION_MAP.get(row["Должность"], row["Должность"])
        skills_raw = row["Навыки"]
        skills = [s.strip() for s in skills_raw.split(",") if s.strip()]
        office = row["Офис"]
        load = int(row["Количество обращений в работе"])

        bu = bu_map.get(office)
        if bu is None:
            logger.warning("Unknown office '%s' for manager '%s'", office, name)
            continue

        key = (name, bu.id)
        if key in by_key:
            mgr = by_key[key]
            mgr.position = position
            mgr.skills = skills
            mgr.current_load = load
        else:
            mgr = Manager(
                name=name,
                position=position,
                skills=skills,
                business_unit_id=bu.id,
                current_load=load,
            )
            session.add(mgr)
            by_key[key] = mgr
            managers.append(mgr)

    await session.flush()
    logger.info("Loaded %d managers (upsert)", len(managers))
    return managers


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    logger.warning("Cannot parse date: '%s'", value)
    return None


def _parse_guid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value.strip())
    except (ValueError, AttributeError):
        logger.warning("Invalid GUID: %r", value)
        return None


async def load_tickets(
    session: AsyncSession, file: io.StringIO
) -> list[Ticket]:
    existing_list = (await session.execute(select(Ticket))).scalars().all()
    by_guid: dict[uuid.UUID, Ticket] = {}
    for t in existing_list:
        if t.client_guid not in by_guid:
            by_guid[t.client_guid] = t

    reader = _make_reader(file)
    for raw_row in reader:
        row = _clean_row(raw_row)
        guid = _parse_guid(row.get("GUID клиента", ""))
        if guid is None:
            continue
        attachment_raw = row.get("Вложения", "")
        attachment_key = attachment_raw if attachment_raw else None

        if guid in by_guid:
            ticket = by_guid[guid]
            ticket.gender = row.get("Пол клиента") or None
            ticket.birth_date = _parse_date(row.get("Дата рождения", ""))
            ticket.description = row["Описание"]
            ticket.attachment_key = attachment_key
            ticket.segment = row["Сегмент клиента"]
            ticket.country = row.get("Страна") or None
            ticket.region = row.get("Область") or None
            ticket.city = row.get("Населённый пункт") or None
            ticket.street = row.get("Улица") or None
            ticket.house = row.get("Дом") or None
            ticket.latitude = None
            ticket.longitude = None
            await session.execute(delete(AIAnalysis).where(AIAnalysis.ticket_id == ticket.id))
            await session.execute(delete(Assignment).where(Assignment.ticket_id == ticket.id))
        else:
            ticket = Ticket(
                client_guid=guid,
                gender=row.get("Пол клиента") or None,
                birth_date=_parse_date(row.get("Дата рождения", "")),
                description=row["Описание"],
                attachment_key=attachment_key,
                segment=row["Сегмент клиента"],
                country=row.get("Страна") or None,
                region=row.get("Область") or None,
                city=row.get("Населённый пункт") or None,
                street=row.get("Улица") or None,
                house=row.get("Дом") or None,
            )
            session.add(ticket)
            by_guid[guid] = ticket

    await session.flush()
    tickets = list(by_guid.values())
    logger.info("Loaded %d tickets (upsert)", len(tickets))
    return tickets
