"""Persist first-class Core rule and provenance identifiers on candidates."""

from alembic import op
import sqlalchemy as sa


revision = "0002_rule_candidate_boundary"
down_revision = "fe1e4ce1da7f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("extraction_candidates", sa.Column("core_rule_id", sa.String(length=64), nullable=True))
    op.add_column("extraction_candidates", sa.Column("core_provenance_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("extraction_candidates", "core_provenance_id")
    op.drop_column("extraction_candidates", "core_rule_id")
