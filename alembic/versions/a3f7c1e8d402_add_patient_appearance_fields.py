"""add_patient_appearance_fields

Revision ID: a3f7c1e8d402
Revises: 09c1ab2b51a9
Create Date: 2026-02-24 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3f7c1e8d402'
down_revision: Union[str, None] = '09c1ab2b51a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('patients', schema=None) as batch_op:
        batch_op.add_column(sa.Column('height', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('weight', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('appearance', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('statement', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('patients', schema=None) as batch_op:
        batch_op.drop_column('statement')
        batch_op.drop_column('appearance')
        batch_op.drop_column('weight')
        batch_op.drop_column('height')
