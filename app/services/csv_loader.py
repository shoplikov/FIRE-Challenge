import csv
import io
import logging
import os
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.business_unit import BusinessUnit
from app.models.manager import Manager
from app.models.ticket import Ticket

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


def _make_reader(file: io.StringIO | None, fallback_path: str):
    """Return (csv.DictReader, file_handle_to_close_or_None)."""
    if file is not None:
        content = file.getvalue().lstrip("\ufeff")
        return csv.DictReader(io.StringIO(content)), None
    fh = open(fallback_path, encoding="utf-8-sig")
    return csv.DictReader(fh), fh


async def load_business_units(
    session: AsyncSession, file: io.StringIO | None = None
) -> dict[str, BusinessUnit]:
    existing = (await session.execute(select(BusinessUnit))).scalars().all()
    if existing:
        return {bu.name: bu for bu in existing}

    path = os.path.join(settings.csv_dir, "business_units.csv")
    reader, fh = _make_reader(file, path)

    result: dict[str, BusinessUnit] = {}
    for raw_row in reader:
        row = _clean_row(raw_row)
        name = row["Офис"]
        address = row["Адрес"]
        bu = BusinessUnit(name=name, address=address)
        session.add(bu)
        result[name] = bu

    if fh:
        fh.close()

    await session.flush()
    logger.info("Loaded %d business units", len(result))
    return result


async def load_managers(
    session: AsyncSession,
    bu_map: dict[str, BusinessUnit],
    file: io.StringIO | None = None,
) -> list[Manager]:
    existing = (await session.execute(select(Manager))).scalars().all()
    if existing:
        return list(existing)

    path = os.path.join(settings.csv_dir, "managers.csv")
    reader, fh = _make_reader(file, path)

    managers: list[Manager] = []
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

        mgr = Manager(
            name=name,
            position=position,
            skills=skills,
            business_unit_id=bu.id,
            current_load=load,
        )
        session.add(mgr)
        managers.append(mgr)

    if fh:
        fh.close()

    await session.flush()
    logger.info("Loaded %d managers", len(managers))
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


async def load_tickets(
    session: AsyncSession, file: io.StringIO | None = None
) -> list[Ticket]:
    existing = (await session.execute(select(Ticket))).scalars().all()
    if existing:
        return list(existing)

    path = os.path.join(settings.csv_dir, "tickets.csv")
    reader, fh = _make_reader(file, path)

    tickets: list[Ticket] = []
    for raw_row in reader:
        row = _clean_row(raw_row)
        attachment_raw = row.get("Вложения", "")
        attachment_key = attachment_raw if attachment_raw else None

        ticket = Ticket(
            client_guid=row["GUID клиента"],
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
        tickets.append(ticket)

    if fh:
        fh.close()

    await session.flush()
    logger.info("Loaded %d tickets", len(tickets))
    return tickets
