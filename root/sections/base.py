from abc import ABC, abstractmethod
from typing import AsyncGenerator

from root.models import Track


class AbstractSection(ABC):
    @abstractmethod
    async def get_tracks_gen(self, query) -> AsyncGenerator[Track, None]: ...
