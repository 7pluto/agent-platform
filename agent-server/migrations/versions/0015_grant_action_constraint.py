"""Constrain resource grant actions to the V1 authorization vocabulary.

Revision ID: 0015_grant_action_constraint
Revises: 0014_ingest_jobs
"""

from alembic import op


revision = "0015_grant_action_constraint"
down_revision = "0014_ingest_jobs"
branch_labels = None
depends_on = None


_ALLOWED = "'[\"VIEW\", \"USE\", \"EDIT\", \"PUBLISH\", \"MANAGE\", \"RUN\"]'::jsonb"


def upgrade() -> None:
    # Earlier builds accepted arbitrary strings. They never matched a runtime
    # permission check, so dropping them is safer than silently translating
    # them into authority.
    op.execute(
        f"""
        DELETE FROM platform_resource_grant
        WHERE jsonb_typeof(actions) <> 'array'
           OR jsonb_array_length(actions) = 0
           OR NOT actions <@ {_ALLOWED}
        """
    )
    op.create_check_constraint(
        "ck_platform_resource_grant_actions_v1",
        "platform_resource_grant",
        f"jsonb_typeof(actions) = 'array' AND jsonb_array_length(actions) > 0 AND actions <@ {_ALLOWED}",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_platform_resource_grant_actions_v1",
        "platform_resource_grant",
        type_="check",
    )
