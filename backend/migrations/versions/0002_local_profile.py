"""Persist explicit local profile selection without moving student data."""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"


def upgrade():
    op.create_table(
        "local_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
    )
    op.create_index("ix_local_profile_owner_id", "local_profile", ["owner_id"])


def downgrade():
    op.drop_table("local_profile")
