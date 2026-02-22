import datetime
import uuid

from pydantic import BaseModel


class AIAnalysisOut(BaseModel):
    id: int
    category: str
    sentiment: str
    priority: int
    language: str
    summary: str

    model_config = {"from_attributes": True}


class AssignmentOut(BaseModel):
    id: int
    manager_id: int
    manager_name: str | None = None
    business_unit_id: int
    business_unit_name: str | None = None
    assigned_at: datetime.datetime
    reason: str | None = None

    model_config = {"from_attributes": True}


class TicketOut(BaseModel):
    id: int
    client_guid: uuid.UUID
    gender: str | None = None
    birth_date: datetime.date | None = None
    description: str
    attachment_key: str | None = None
    attachment_url: str | None = None
    segment: str
    country: str | None = None
    region: str | None = None
    city: str | None = None
    street: str | None = None
    house: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    created_at: datetime.datetime | None = None
    ai_analysis: AIAnalysisOut | None = None
    assignment: AssignmentOut | None = None

    model_config = {"from_attributes": True}


class TicketListOut(BaseModel):
    items: list[TicketOut]
    total: int


class DashboardStats(BaseModel):
    total_tickets: int
    assigned_tickets: int
    avg_priority: float
    categories: dict[str, int]
    sentiments: dict[str, int]
    languages: dict[str, int]
    offices: dict[str, int]
    segments: dict[str, int]


class PipelineResult(BaseModel):
    tickets_loaded: int
    tickets_analyzed: int
    tickets_assigned: int
    errors: list[str]
    tickets: list[TicketOut]


# AI Chart Assistant
class AIChartRequest(BaseModel):
    query: str


class ChartSeries(BaseModel):
    name: str
    values: list[int]


class ChartData2D(BaseModel):
    labels: list[str]
    series: list[ChartSeries]


class AIChartResponse(BaseModel):
    title: str
    chart_type: str
    data_1d: dict[str, int] | None = None
    data_2d: ChartData2D | None = None
