"""move_position_from_gameplayer_to_patient

Revision ID: b3a1f7c82d45
Revises: 964d770c3a28
Create Date: 2026-02-14 20:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3a1f7c82d45'
down_revision: Union[str, None] = '964d770c3a28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add position columns to patients
    op.add_column('patients', sa.Column('current_region_id', sa.String(length=32), nullable=True))
    op.add_column('patients', sa.Column('current_location_id', sa.String(length=32), nullable=True))
    op.create_foreign_key('fk_patient_region', 'patients', 'regions', ['current_region_id'], ['id'])
    op.create_foreign_key('fk_patient_location', 'patients', 'locations', ['current_location_id'], ['id'])

    # Migrate existing position data from game_players to patients (via active_patient_id)
    op.execute("""
        UPDATE patients SET
            current_region_id = (
                SELECT gp.current_region_id FROM game_players gp
                WHERE gp.active_patient_id = patients.id
            ),
            current_location_id = (
                SELECT gp.current_location_id FROM game_players gp
                WHERE gp.active_patient_id = patients.id
            )
    """)

    # Remove position columns from game_players
    op.drop_constraint(None, 'game_players', type_='foreignkey')
    op.drop_column('game_players', 'current_region_id')
    op.drop_column('game_players', 'current_location_id')


def downgrade() -> None:
    # Add position columns back to game_players
    op.add_column('game_players', sa.Column('current_region_id', sa.String(length=32), nullable=True))
    op.add_column('game_players', sa.Column('current_location_id', sa.String(length=32), nullable=True))
    op.create_foreign_key(None, 'game_players', 'regions', ['current_region_id'], ['id'])
    op.create_foreign_key(None, 'game_players', 'locations', ['current_location_id'], ['id'])

    # Migrate position data back from patients to game_players
    op.execute("""
        UPDATE game_players SET
            current_region_id = (
                SELECT p.current_region_id FROM patients p
                WHERE p.id = game_players.active_patient_id
            ),
            current_location_id = (
                SELECT p.current_location_id FROM patients p
                WHERE p.id = game_players.active_patient_id
            )
    """)

    # Remove position columns from patients
    op.drop_constraint('fk_patient_location', 'patients', type_='foreignkey')
    op.drop_constraint('fk_patient_region', 'patients', type_='foreignkey')
    op.drop_column('patients', 'current_location_id')
    op.drop_column('patients', 'current_region_id')
