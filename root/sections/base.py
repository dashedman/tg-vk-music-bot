from abc import ABC, abstractmethod
from typing import AsyncGenerator

from root.models import Track


class AbstractSection(ABC):
    @abstractmethod
    async def get_tracks_gen(self, query: str) -> AsyncGenerator[Track, None]: ...

    @abstractmethod
    async def get_new_songs(self) -> AsyncGenerator[Track, None]: ...

    @abstractmethod
    async def get_popular_songs(self) -> AsyncGenerator[Track, None]: ...
