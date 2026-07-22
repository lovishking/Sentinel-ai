"""initial

Revision ID: 6ac04866841a
Revises: 
Create Date: 2026-07-19 21:41:14.539280

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6ac04866841a'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    op.create_table(
        'incidents',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.Enum('OPEN', 'INVESTIGATING', 'RESOLVED', name='incidentstatus'), nullable=True),
        sa.Column('severity', sa.String(), nullable=True),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('source_type', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True)
    )
    
    from pgvector.sqlalchemy import Vector
    from sqlalchemy.dialects.postgresql import JSONB

    op.create_table(
        'evidence',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('incident_id', sa.Integer(), sa.ForeignKey('incidents.id'), nullable=False),
        sa.Column('source_type', sa.Enum('LOG', 'METRIC', 'K8S_EVENT', 'DEPLOY', name='evidencesourcetype'), nullable=False),
        sa.Column('raw_content', sa.Text(), nullable=False),
        sa.Column('structured_content', JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('embedding', Vector(1536), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True)
    )

    op.create_table(
        'agent_runs',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('incident_id', sa.Integer(), sa.ForeignKey('incidents.id'), nullable=False),
        sa.Column('agent_name', sa.String(), nullable=False),
        sa.Column('input', JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('output', JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True)
    )

    op.create_table(
        'fixes',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('incident_id', sa.Integer(), sa.ForeignKey('incidents.id'), nullable=False),
        sa.Column('diff_content', sa.Text(), nullable=False),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('test_results', JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True)
    )

    op.create_table(
        'pull_requests',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('fix_id', sa.Integer(), sa.ForeignKey('fixes.id'), nullable=False),
        sa.Column('repo', sa.String(), nullable=False),
        sa.Column('pr_number', sa.Integer(), nullable=True),
        sa.Column('pr_url', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('pull_requests')
    op.drop_table('fixes')
    op.drop_table('agent_runs')
    op.drop_table('evidence')
    op.drop_table('incidents')
    op.execute("DROP TYPE IF EXISTS evidencesourcetype")
    op.execute("DROP TYPE IF EXISTS incidentstatus")
    op.execute("DROP EXTENSION IF EXISTS vector")
