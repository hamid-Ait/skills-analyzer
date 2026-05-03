"""Rebuild linkedin_experience_summary from linkedin_experience JSONB.

Changes format from multi-line per role to single-line:
  "Position @ Company · Duration · Location"

Revision ID: 003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session


revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def _build_summary(experience: list[dict]) -> str:
    """Rebuild experience summary in the new format."""
    if not experience:
        return "—"
    lines = []
    for exp in experience[:5]:
        position = exp.get("position") or exp.get("title") or ""
        company = exp.get("companyName") or ""
        duration = exp.get("duration") or ""
        location = exp.get("location") or ""
        role = position
        if company:
            role = f"{role} @ {company}" if role else company
        detail_parts = [p for p in [duration, location] if p]
        if detail_parts:
            role = f"{role} · {' · '.join(detail_parts)}" if role else " · ".join(detail_parts)
        if role:
            lines.append(role)
    return "\n".join(lines) if lines else "—"


def upgrade() -> None:
    conn = op.get_bind()
    # Fetch all people with linkedin_experience JSONB data
    rows = conn.execute(
        sa.text(
            "SELECT id, linkedin_experience FROM people "
            "WHERE linkedin_experience IS NOT NULL"
        )
    ).fetchall()

    for row in rows:
        person_id, experience = row
        if not isinstance(experience, list):
            continue
        summary = _build_summary(experience)
        conn.execute(
            sa.text(
                "UPDATE people SET linkedin_experience_summary = :summary "
                "WHERE id = :id"
            ),
            {"summary": summary, "id": person_id},
        )


def downgrade() -> None:
    # No rollback — old format is lossy anyway
    pass