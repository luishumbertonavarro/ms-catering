"""mensajeria: outbox e inbox

Revision ID: 7c1e2a9b4d10
Revises: 126a03743ded
Create Date: 2026-10-26 23:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '7c1e2a9b4d10'
down_revision: Union[str, Sequence[str], None] = '126a03743ded'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Transactional Outbox (eventos por publicar) e inbox de idempotencia (eventos consumidos)."""
    op.create_table('outbox',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tipo', sa.String(length=100), nullable=False),
    sa.Column('routing_key', sa.String(length=100), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('ocurrido_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('publicado_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('intentos', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('ultimo_error', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    # El relay solo busca pendientes: índice parcial.
    op.create_index(
        'ix_outbox_pendientes', 'outbox', ['ocurrido_en'],
        postgresql_where=sa.text('publicado_en IS NULL'),
    )
    op.create_table('eventos_procesados',
    sa.Column('message_id', sa.String(length=100), nullable=False),
    sa.Column('routing_key', sa.String(length=100), nullable=False),
    sa.Column('procesado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('message_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('eventos_procesados')
    op.drop_index('ix_outbox_pendientes', table_name='outbox')
    op.drop_table('outbox')
