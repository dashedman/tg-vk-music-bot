import asyncio
import logging
import time
from enum import IntEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from root.constants import Constants
from root.db_models import CachedTrack
from root.models import Track


class CacheAnswer(IntEnum):
    FromCache = 1
    FromOrigin = 2


class TracksCache:
    def __init__(self, db_engine: AsyncEngine, constants: Constants):
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
            return CacheAnswer.FromCache, file_id

        self.already_on_loading.add(track_id)
        time_start = time.time()
        track_data = await track.load_audio()
        time_end = time.time()
        self.logger.info(
            'Track loaded in %.2f sec, %.2f Mb',
            time_end - time_start,
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
