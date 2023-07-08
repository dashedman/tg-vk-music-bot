import asyncio
import logging
import time
from enum import IntEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

import root
from root.constants import Constants
from root.db_models import CachedTrack
from root.models import Track


class CacheAnswer(IntEnum):
    FromCache = 1
    FromOrigin = 2


class TracksCache:
    def __init__(self, bot: 'root.MusicBot', db_engine: AsyncEngine, constants: Constants):
        self.bot = bot
        self.db_engine = db_engine
        self.already_on_loading = set()

        self.constants = constants
        self.logger = logging.getLogger('cache')

    async def check_cache(self, track: Track) -> tuple[CacheAnswer, str | bytes]:
        # check cache
        track_id = track.get_id()
        if track_id in self.already_on_loading:
            while track_id in self.already_on_loading:
                await asyncio.sleep(0)

        async with self.db_engine.connect() as conn:
            file_id: str = await conn.scalar(
                select(
                    CachedTrack.file_id
                ).where(
                    CachedTrack.id == track_id
                ).limit(1)
            )

        if file_id is not None:
            self.logger.info('Track (%s) taken from cache', track.full_name)
            return CacheAnswer.FromCache, file_id

        self.already_on_loading.add(track_id)
        self.logger.info('Starting load track: %s', track.full_name)
        time_start = time.time()
        await self.bot.vk.limiter.wait()
        time_queue = time.time()
        if time_queue - time_start > 0.1:
            self.logger.warning(
                'Staying in queue for %.2f sec (%s)',
                time_queue - time_start, track.full_name
            )
        track_data = await track.load_audio()
        time_end = time.time()
        self.logger.info(
            'Track (%s) loaded in %.2f sec, %.2f Mb', track.full_name,
            time_end - time_queue,
            len(track_data) / self.constants.MEGABYTE_SIZE
        )
        return CacheAnswer.FromOrigin, track_data

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

        self.already_on_loading.remove(track_id)
