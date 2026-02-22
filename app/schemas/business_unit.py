from pydantic import BaseModel


class BusinessUnitOut(BaseModel):
    id: int
    name: str
    address: str
    latitude: float | None = None
    longitude: float | None = None

    model_config = {"from_attributes": True}
