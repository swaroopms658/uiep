"""initial schema

Revision ID: 20260427_01
Revises:
Create Date: 2026-04-27 11:45:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260427_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)

    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("progress", sa.Float(), nullable=True),
        sa.Column("total_pages", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_processing_jobs_id"), "processing_jobs", ["id"], unique=False)

    op.create_table(
        "transactions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("txn_date", sa.DateTime(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("merchant", sa.String(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("txn_type", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("upi_id", sa.String(), nullable=True),
        sa.Column("is_recurring", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_transactions_category"), "transactions", ["category"], unique=False)
    op.create_index(op.f("ix_transactions_id"), "transactions", ["id"], unique=False)
    op.create_index(op.f("ix_transactions_merchant"), "transactions", ["merchant"], unique=False)
    op.create_index(op.f("ix_transactions_txn_date"), "transactions", ["txn_date"], unique=False)
    op.create_index(op.f("ix_transactions_upi_id"), "transactions", ["upi_id"], unique=False)
    op.create_index(op.f("ix_transactions_user_id"), "transactions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_transactions_user_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_upi_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_txn_date"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_merchant"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_category"), table_name="transactions")
    op.drop_table("transactions")

    op.drop_index(op.f("ix_processing_jobs_id"), table_name="processing_jobs")
    op.drop_table("processing_jobs")

    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_table("users")
