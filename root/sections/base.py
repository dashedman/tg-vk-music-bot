from abc import ABC, abstractmethod
from typing import AsyncGenerator

import root
import root.models


class AbstractSection(ABC):
    bot: 'root.MusicBot' = NotImplemented

    @abstractmethod
    async def get_tracks_gen(self, query: str) -> AsyncGenerator['root.models.Track', None]: ...

    @abstractmethod
    async def get_new_songs(self) -> AsyncGenerator['root.models.Track', None]: ...

    @abstractmethod
    async def get_popular_songs(self) -> AsyncGenerator['root.models.Track', None]: ...
