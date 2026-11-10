"""create qa_logs table

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-11 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "qa_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("cited_chunk_ids", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_qa_logs_id"), "qa_logs", ["id"], unique=False)
    op.create_index(op.f("ix_qa_logs_user_id"), "qa_logs", ["user_id"], unique=False)
    op.create_index(op.f("ix_qa_logs_created_at"), "qa_logs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_qa_logs_created_at"), table_name="qa_logs")
    op.drop_index(op.f("ix_qa_logs_user_id"), table_name="qa_logs")
    op.drop_index(op.f("ix_qa_logs_id"), table_name="qa_logs")
    op.drop_table("qa_logs")
