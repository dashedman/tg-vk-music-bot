"""add chat table

Revision ID: 88f0b269a679
Revises: d3ffa57408c4
Create Date: 2023-07-08 13:46:30.831966

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '88f0b269a679'
down_revision = 'd3ffa57408c4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'chats',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('is_free_mode', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('chats')
