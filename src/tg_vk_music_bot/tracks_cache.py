import asyncio
import logging
from enum import IntEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
import aiogram.types as agt

import tg_vk_music_bot
import tg_vk_music_bot.ui_constants as uic
from tg_vk_music_bot.db_models import CachedTrack
from tg_vk_music_bot.models import Track


class CacheAnswer(IntEnum):
    FromCache = 1
    FromOrigin = 2


class TracksCache:
    def __init__(self, bot: 'tg_vk_music_bot.MusicBot'):
        self.bot = bot
        self.logger = logging.getLogger('cache')

    @property
    def db_engine(self):
        return self.bot.db_engine

    @property
    def constants(self):
        return self.bot.constants

    @property
    def loads_demon(self):
        return self.bot.loads_demon

    @property
    def tg_bot(self):
        return self.bot.telegram

    async def send_track(self, track: Track, chat: agt.Chat):
        if await self.check_cache_and_send(track, chat):
            return

        try:
            await self.loads_demon.push(chat, track)
        except asyncio.QueueFull:
            await self.tg_bot.send_message(chat.id, uic.queue_is_full())

    async def check_cache_and_send(self, track: Track, chat: agt.Chat) -> bool:
        file_id = await self.get_cache(track)
        if file_id is not None:
            self.logger.info('Track (%s) taken from cache', track.full_name)
            await self.tg_bot.send_audio(
                chat_id=chat.id,
                audio=file_id,
                caption=self.bot.signer.get_signature(track.performer),
                parse_mode='html',
            )
            return True
        return False

    async def get_cache(self, track: Track) -> str | None:
        track_id = track.get_id()
        async with self.db_engine.connect() as conn:
            file_id: str = await conn.scalar(
                select(
                    CachedTrack.file_id
                ).where(
                    CachedTrack.id == track_id
                ).limit(1)
            )

        return file_id

    async def check_cache(self, track_ids: list[str]) -> list[str]:
        async with self.db_engine.connect() as conn:
            exist_tracks: list[str] = (await conn.execute(
                select(
                    CachedTrack.id
                ).where(
                    CachedTrack.id.in_(track_ids)
                )
            )).scalars().all()

        return exist_tracks

    async def save_cache(self, track: Track, file_id: str):
        track_id = track.get_id()
        async_session = async_sessionmaker(
            self.db_engine,
            expire_on_commit=False
        )

        async with async_session() as session:
            async with session.begin():
                session.add(
                    CachedTrack(
                        track_id,
                        file_id,
                    )
                )
