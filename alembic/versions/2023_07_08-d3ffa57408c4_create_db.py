"""create db

Revision ID: d3ffa57408c4
Revises: 
Create Date: 2023-07-08 09:51:41.969244

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd3ffa57408c4'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('cached_tracks',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('file_id', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('cached_tracks')
