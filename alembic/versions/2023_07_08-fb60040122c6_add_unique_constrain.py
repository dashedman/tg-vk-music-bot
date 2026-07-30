"""add unique constrain

Revision ID: fb60040122c6
Revises: 88f0b269a679
Create Date: 2023-07-08 14:04:22.373987

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fb60040122c6'
down_revision = '88f0b269a679'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('cached_tracks', schema=None) as batch_op:
        batch_op.create_unique_constraint('unique_file_id', ['file_id'])


def downgrade() -> None:
    with op.batch_alter_table('cached_tracks', schema=None) as batch_op:
        batch_op.drop_constraint('unique_file_id', type_='unique')

