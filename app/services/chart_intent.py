"""Parse natural-language chart queries into structured ChartIntent using LLM."""
from typing import Literal

from pydantic import BaseModel

from app.services.nlp import _get_llm

DIMENSIONS = (
    "city",
    "region",
    "country",
    "category",
    "sentiment",
    "language",
    "segment",
    "office",
)

CHART_INTENT_SYSTEM = """\
You are a chart intent parser for a ticket analytics dashboard.

Available dimensions (use exactly these strings):
- city, region, country (ticket location)
- category, sentiment, language (from AI analysis: e.g. Жалоба, Консультация; Позитивный/Нейтральный/Негативный; RU/KZ/ENG)
- segment (ticket segment: VIP, Mass, Priority)
- office (assigned business unit / office name)

The user will ask in natural language (Russian or English) for a chart. Examples:
- "Покажи распределение типов обращений по городам" -> group_by=city, breakdown_by=category
- "Обращения по офисам" -> group_by=office
- "Языки по сегментам" -> group_by=segment, breakdown_by=language

Output:
- group_by: exactly one dimension from the list above (primary grouping).
- breakdown_by: optional second dimension for 2D chart; omit or null for simple 1D chart.
- chart_type: "bar", "stacked_bar", or "pie". Prefer "bar" for 1D, "stacked_bar" for 2D.
- title: short chart title in the same language as the query (e.g. Russian)."""


class ChartIntent(BaseModel):
    group_by: Literal[
        "city", "region", "country", "category", "sentiment", "language", "segment", "office"
    ]
    breakdown_by: Literal[
        "city", "region", "country", "category", "sentiment", "language", "segment", "office"
    ] | None = None
    chart_type: Literal["bar", "stacked_bar", "pie"] = "bar"
    title: str = ""


async def parse_chart_query(query: str) -> ChartIntent:
    """Parse user text query into structured ChartIntent via LLM."""
    llm = _get_llm().with_structured_output(ChartIntent, method="json_schema")
    result = await llm.ainvoke([
        {"role": "system", "content": CHART_INTENT_SYSTEM},
        {"role": "user", "content": query.strip() or "Распределение обращений"},
    ])
    return result
