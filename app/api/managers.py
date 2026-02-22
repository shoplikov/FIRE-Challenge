from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.models.manager import Manager
from app.schemas.manager import ManagerOut

router = APIRouter(prefix="/api/managers", tags=["managers"])


@router.get("", response_model=list[ManagerOut])
async def list_managers(session: AsyncSession = Depends(get_session)):
    query = select(Manager).options(selectinload(Manager.business_unit)).order_by(Manager.id)
    managers = (await session.execute(query)).scalars().all()
    return [
        ManagerOut(
            id=m.id,
            name=m.name,
            position=m.position,
            skills=m.skills,
            business_unit_id=m.business_unit_id,
            business_unit_name=m.business_unit.name,
            current_load=m.current_load,
        )
        for m in managers
    ]
