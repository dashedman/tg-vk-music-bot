import asyncio
import io
import logging
import time
from dataclasses import dataclass

import aiogram.types as agt

import root
import root.ui_constants as uic
from root.models import Track
from root.tracks_cache import CacheAnswer


@dataclass
class LoadTask:
    track: Track
    chat: agt.Chat
    message: 'agt.Message' = None

    async def wait_for_message(self):
        while self.message is None:
            await asyncio.sleep(0)


class LoadsDemon:

    def __init__(self, bot: 'root.MusicBot', queue_size: int = 1000, workers: int = 1):
        self.bot = bot
        self.queue: asyncio.Queue[LoadTask] = asyncio.Queue(maxsize=queue_size)
        self.workers = workers
        self.alive = False
        self.current_in_loads = set()
        self.logger = logging.getLogger('loads_demon')

    @property
    def constants(self):
        return self.bot.constants

    @property
    def cache(self):
        return self.bot.tracks_cache

    @property
    def tg_bot(self):
        return self.bot.telegram.bot

    async def push(self, chat: agt.Chat, track: Track):
        # fast load with no queue
        task = LoadTask(track, chat)
        self.queue.put_nowait(task)
        message = await self.tg_bot.send_message(
            chat_id=chat.id,
            text=uic.add_to_download_queue(track.title, track.performer),
        )
        task.message = message

    async def serve(self):
        self.alive = True
        self.logger.info('Start works')
        workers_coro = [
            self.worker(wid)
            for wid in range(1, self.workers + 1)
        ]
        await asyncio.gather(*workers_coro)
        self.logger.info('Finish')

    async def worker(self, worker_id: int):
        self.logger.info('Start worker: %s', worker_id)
        while self.alive:
            load_task = await self.queue.get()
            await load_task.wait_for_message()
            await self._load_track(
                load_task.message,
                load_task.chat,
                load_task.track
            )
        self.logger.info('End worker: %s', worker_id)

    async def _load_track(self, message: agt.Message, chat: agt.Chat, track: Track):
        if await self.cache.check_cache_and_send(track, chat):
            await message.delete()
            return

        if await self.check_in_curent_loads(track, chat):
            await message.delete()
            return

        self.current_in_loads.add(track.get_id())
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

        file_id = await self.send_track(message, track, track_data)
        await self.bot.tracks_cache.save_cache(
            track,
            file_id=file_id,
        )
        self.current_in_loads.remove(track.get_id())

    async def send_track(self, message: agt.Message, track: Track, track_data: bytes) -> str:
        _, _, message = await asyncio.gather(
            message.answer_chat_action('upload_document'),
            message.delete(),
            message.answer_audio(
                audio=agt.InputFile(
                    io.BytesIO(track_data),
                    filename=f"{track.performer[:32]}_{track.title[:32]}.mp3",
                ),
                title=track.title,
                performer=track.performer,
                caption=uic.SIGNATURE,
                duration=track.duration,
                parse_mode='html',
            )
        )
        return message.audio.file_id

    async def check_in_curent_loads(self, track: Track, chat: agt.Chat) -> bool:
        if (track_id := track.get_id()) in self.current_in_loads:
            # wait until will be loaded
            while track_id in self.current_in_loads:
                await asyncio.sleep(0)
            return await self.cache.check_cache_and_send(track, chat)
        return False




