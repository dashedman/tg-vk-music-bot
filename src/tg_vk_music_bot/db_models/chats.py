from sqlalchemy import Integer, Boolean
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from .base import Base


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(Integer(), primary_key=True)
    is_free_mode: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)

    def __init__(self, chat_id, mode):
        self.id = chat_id
        self.is_free_mode = mode

        super().__init__()
