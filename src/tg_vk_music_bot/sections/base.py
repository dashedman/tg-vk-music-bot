from abc import ABC, abstractmethod
from typing import AsyncGenerator

import tg_vk_music_bot.models


class AbstractSection(ABC):
    bot: 'tg_vk_music_bot.MusicBot' = NotImplemented

    @abstractmethod
    async def get_tracks_gen(self, query: str) -> AsyncGenerator['tg_vk_music_bot.models.Track', None]: ...

    @abstractmethod
    async def get_new_songs(self) -> AsyncGenerator['tg_vk_music_bot.models.Track', None]: ...

    @abstractmethod
    async def get_popular_songs(self) -> AsyncGenerator['tg_vk_music_bot.models.Track', None]: ...

    @abstractmethod
    async def get_albums_gen(self, query: str) -> AsyncGenerator['tg_vk_music_bot.models.Album', None]: ...
