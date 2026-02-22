import asyncio
import logging
import os
from typing import Literal

from langchain_openai import ChatOpenAI
from langfuse.langchain import CallbackHandler
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
- Category definitions:
  - "Спам": unsolicited advertising, mass/templated promotions, irrelevant content, repeated messages, suspicious links/invites (e.g. casino, betting, crypto pumps, "quick earnings", "join channel", "DM me"), or any message unrelated to support request.
  - "Мошеннические действия": user reports scam/fraud, unauthorized transactions/access, account takeover, phishing, identity theft, or asks to block fraudulent activity.
  - "Неработоспособность приложения": app/site does not work, errors, crashes, login failures, broken features.
  - "Смена данных": requests to change personal/profile/account data.
  - "Претензия": formal claim/dispute with demand for review/compensation.
  - "Жалоба": complaint about service quality/employee/process without formal claim.
  - "Консультация": information request/how-to/general question.
- Classification priority:
  - If the message is irrelevant/promotional/mass-like, choose "Спам" even if sentiment looks neutral.
  - If both spam-like and fraud-reporting signals are present, choose "Мошеннические действия" only when the user is clearly reporting victimization or unauthorized activity; otherwise choose "Спам".
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
    callbacks = _get_langfuse_callbacks()
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
        callbacks=callbacks if callbacks else None,
    )


def _get_langfuse_callbacks() -> list[CallbackHandler]:
    if not settings.langfuse_enabled:
        return []

    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.warning(
            "Langfuse is enabled, but credentials are missing. Tracing is disabled."
        )
        return []

    # Langfuse v2 CallbackHandler reads from env vars only
    base_url = settings.langfuse_base_url or settings.langfuse_host or "https://cloud.langfuse.com"
    os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
    os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key
    os.environ["LANGFUSE_HOST"] = base_url
    os.environ["LANGFUSE_BASE_URL"] = base_url
    return [CallbackHandler()]


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
