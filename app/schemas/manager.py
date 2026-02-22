from pydantic import BaseModel


class ManagerOut(BaseModel):
    id: int
    name: str
    position: str
    skills: list[str]
    business_unit_id: int
    business_unit_name: str | None = None
    current_load: int

    model_config = {"from_attributes": True}
