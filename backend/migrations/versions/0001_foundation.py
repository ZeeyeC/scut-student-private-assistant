"""Student aggregates and FastAPI Users session tables."""
from alembic import op
import sqlalchemy as sa
from fastapi_users_db_sqlalchemy.generics import GUID

revision = "0001"
down_revision = None


def upgrade():
    op.create_table("user", sa.Column("id", GUID(), primary_key=True), sa.Column("email", sa.String(320), nullable=False), sa.Column("hashed_password", sa.String(1024), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("is_superuser", sa.Boolean(), nullable=False), sa.Column("is_verified", sa.Boolean(), nullable=False))
    op.create_index("ix_user_email", "user", ["email"], unique=True)
    op.create_table("accesstoken", sa.Column("token", sa.String(43), primary_key=True), sa.Column("user_id", GUID(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_accesstoken_created_at", "accesstoken", ["created_at"])
    op.create_table("resources", sa.Column("id", sa.String(), primary_key=True), sa.Column("owner_id", sa.String(), nullable=False), sa.Column("kind", sa.String(), nullable=False), sa.Column("revision", sa.Integer(), nullable=False), sa.Column("data", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_resources_owner_id", "resources", ["owner_id"])
    op.create_index("ix_resources_kind", "resources", ["kind"])
    op.create_table("receipts", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("owner_id", sa.String(), nullable=False), sa.Column("scope", sa.String(), nullable=False), sa.Column("key", sa.String(), nullable=False), sa.Column("payload_hash", sa.String(), nullable=False), sa.Column("result", sa.JSON(), nullable=False), sa.UniqueConstraint("owner_id", "scope", "key"))


def downgrade():
    for table in ("receipts", "resources", "accesstoken", "user"):
        op.drop_table(table)
