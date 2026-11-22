"""add subscriptions table

Revision ID: a2f3e7b9c401
Revises: d1b0c82c90a1
Create Date: 2026-10-30
"""
from alembic import op
import sqlalchemy as sa

revision = "a2f3e7b9c401"
down_revision = "d1b0c82c90a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("plan", sa.String(20), nullable=False, server_default="free"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("payment_id", sa.String(255), nullable=True),
        sa.Column("payment_provider", sa.String(50), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("subscriptions")
