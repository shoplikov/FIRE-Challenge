"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-02-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "business_units",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
    )

    op.create_table(
        "managers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("position", sa.String(100), nullable=False),
        sa.Column("skills", sa.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column(
            "business_unit_id",
            sa.Integer(),
            sa.ForeignKey("business_units.id"),
            nullable=False,
        ),
        sa.Column("current_load", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_guid", UUID(as_uuid=True), nullable=False),
        sa.Column("gender", sa.String(50), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("attachment_key", sa.String(500), nullable=True),
        sa.Column("segment", sa.String(50), nullable=False),
        sa.Column("country", sa.String(255), nullable=True),
        sa.Column("region", sa.String(255), nullable=True),
        sa.Column("city", sa.String(255), nullable=True),
        sa.Column("street", sa.String(255), nullable=True),
        sa.Column("house", sa.String(50), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "ai_analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "ticket_id",
            sa.Integer(),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("sentiment", sa.String(50), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(10), nullable=False, server_default="RU"),
        sa.Column("summary", sa.Text(), nullable=False),
    )

    op.create_table(
        "assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "ticket_id",
            sa.Integer(),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column(
            "ai_analysis_id",
            sa.Integer(),
            sa.ForeignKey("ai_analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "manager_id",
            sa.Integer(),
            sa.ForeignKey("managers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "business_unit_id",
            sa.Integer(),
            sa.ForeignKey("business_units.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("assignments")
    op.drop_table("ai_analyses")
    op.drop_table("tickets")
    op.drop_table("managers")
    op.drop_table("business_units")
