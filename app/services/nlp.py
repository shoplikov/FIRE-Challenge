import asyncio
import logging
from typing import Literal

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.ticket import AIAnalysis, Ticket

logger = logging.getLogger(__name__)

SEMAPHORE = asyncio.Semaphore(5)

SYSTEM_PROMPT = """\
You are an expert customer support analyst for a financial brokerage company (Freedom Finance / Freedom Broker) operating in Kazakhstan.

Analyze the customer ticket below and extract structured information.

Rules:
- category: Choose EXACTLY ONE from the list. Pick the BEST match.
- sentiment: Evaluate the emotional tone of the customer's message.
- priority: 1 = lowest urgency, 10 = highest urgency. Consider: threats, financial loss, blocked accounts, fraud = high priority. General questions = low priority.
- language: Detect the PRIMARY language. If the text is mostly in Russian, output "RU". If Kazakh, output "KZ". If English, output "ENG". Default to "RU" if unclear.
- summary: Write 1-2 sentences summarizing the issue, then add a recommendation for the manager (e.g. "Рекомендация: ...").

Output ONLY valid JSON matching the schema."""


class TicketAnalysis(BaseModel):
    category: Literal[
        "Жалоба",
        "Смена данных",
        "Консультация",
        "Претензия",
        "Неработоспособность приложения",
        "Мошеннические действия",
        "Спам",
    ]
    sentiment: Literal["Позитивный", "Нейтральный", "Негативный"]
    priority: int = Field(ge=1, le=10)
    language: Literal["KZ", "ENG", "RU"]
    summary: str


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )


async def analyze_ticket(description: str) -> TicketAnalysis:
    llm = _get_llm().with_structured_output(TicketAnalysis, method="json_schema")
    async with SEMAPHORE:
        result = await llm.ainvoke([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": description},
        ])
    return result


async def analyze_all_tickets(
    session: AsyncSession, tickets: list[Ticket]
) -> list[AIAnalysis]:
    unanalyzed = [t for t in tickets if t.ai_analysis is None]
    if not unanalyzed:
        logger.info("All tickets already analyzed")
        return []

    logger.info("Analyzing %d tickets with LLM...", len(unanalyzed))

    async def _process(ticket: Ticket) -> AIAnalysis | None:
        try:
            result = await analyze_ticket(ticket.description)
            analysis = AIAnalysis(
                ticket_id=ticket.id,
                category=result.category,
                sentiment=result.sentiment,
                priority=result.priority,
                language=result.language,
                summary=result.summary,
            )
            session.add(analysis)
            return analysis
        except Exception:
            logger.exception("Failed to analyze ticket %d", ticket.id)
            return None

    results = await asyncio.gather(*[_process(t) for t in unanalyzed])
    analyses = [a for a in results if a is not None]
    await session.flush()
    logger.info("Analyzed %d / %d tickets", len(analyses), len(unanalyzed))
    return analyses
