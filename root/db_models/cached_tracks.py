from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from .base import Base


class CachedTrack(Base):
    __tablename__ = "cached_tracks"

    id: Mapped[str] = mapped_column(String(), primary_key=True)
    file_id: Mapped[str] = mapped_column(String())

    def __init__(self, track_id, file_id):
        self.id = track_id
        self.file_id = file_id

        super().__init__()
