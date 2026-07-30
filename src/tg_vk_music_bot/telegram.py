import asyncio
# telegram api
import html
import time
from asyncio import Future
from typing import Coroutine

import asynciolimiter
import cachetools

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Filter
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import chat_member
import aiogram.types as agt

from tg_vk_music_bot.models import Track

# from tg_vk_music_bot.utils import ThrottlingMiddleware


# TODO: move to telegram utils
class AdminFilter(Filter):
    async def __call__(self, message: Message) -> bool:
        return isinstance(message.from_user, chat_member.ADMINS)


# TODO: move to telegram utils
def is_command(message: Message):
    """
    Check message text is command
    :return: bool
    """
    text = message.text or message.caption
    return text and text.startswith("/")


# TODO: move to telegram utils
def get_full_command(message: Message):
    """
    Split command and args
    :return: tuple of (command, args)
    """
    if is_command(message):
        text = message.text or message.caption
        command, *args = text.split(maxsplit=1)
        args = args[0] if args else ""
        return command, args


class TelegramHandler:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger

        self.logger.info("Telegram autentification...")
        self.bot = Bot(token=self.config['token'], default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.storage = MemoryStorage()
        self.dispatcher = Dispatcher(storage=self.storage)

        self.alive = False
        self.queue: asyncio.Queue[tuple[int, Coroutine, Future]] = asyncio.Queue(maxsize=50000)
        self.limiters_storage = cachetools.TTLCache(maxsize=10000, ttl=180)
        self.global_limiter = asynciolimiter.Limiter(30)

        # TODO
        # middleware = ThrottlingMiddleware(throttling_rate_limit=1.5, silence_cooldown=30)
        # self.dispatcher.middleware.setup(middleware)

    @staticmethod
    def get_inline_keyboard(commands_to_tracks: dict[int, 'Track']):
        inline_keyboard = []
        for command_id, track in commands_to_tracks:
            duration = time.gmtime(track.duration)
            inline_keyboard.append([
                InlineKeyboardButton(
                    text=html.unescape(
                        f"{track.performer} - {track.title} ({duration.tm_min}:{duration.tm_sec:02})"
                        .replace("$#", "&#")
                    ),
                    callback_data=str(command_id),
                )
            ])
        return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

    async def serve(self):
        while True:
            chat_id, coro, fut = await self.queue.get()
            try:
                chat_limiter = self.limiters_storage[chat_id]
            except KeyError:
                chat_limiter = asynciolimiter.Limiter(
                    rate=20 / 60
                )  # 20 per minute
                self.limiters_storage[chat_id] = chat_limiter

            await chat_limiter.wait()
            await self.global_limiter.wait()
            asyncio.create_task(self.wrap_fut(coro, fut))

    async def wrap_fut(self, coro, fut):
        try:
            coro_result = await coro
        except BaseException as e:
            fut.set_exception(e)
        else:
            fut.set_result(coro_result)
        self.logger.info('Fut set. Queue size: %s', self.queue.qsize())

    async def _send_coro(self, chat_id: int, coro: Coroutine):
        fut = asyncio.get_running_loop().create_future()
        self.queue.put_nowait((chat_id, coro, fut))
        return await fut

    async def send_message(self, chat_id, *args, **kw):
        return await self._send_coro(
            chat_id,
            self.bot.send_message(chat_id, *args, **kw),
        )

    async def answer_message(self, msg: agt.Message, *args, **kw):
        return await self.send_message(msg.chat.id, *args, **kw)

    async def send_audio(self, chat_id, *args, **kw):
        return await self._send_coro(
            chat_id,
            self.bot.send_audio(chat_id, *args, **kw),
        )

    async def answer_audio(self, msg: agt.Message, *args, **kw):
        return await self.send_audio(msg.chat.id, *args, **kw)

    async def delete_message(self, msg: agt.Message):
        return await self._send_coro(
            msg.chat.id,
            msg.delete(),
        )

    async def send_chat_action(self, chat_id, *args, **kw):
        return await self._send_coro(
            chat_id,
            self.bot.send_chat_action(chat_id, *args, **kw),
        )

    async def answer_chat_action(self, msg: agt.Message, *args, **kw):
        return await self.send_chat_action(msg.chat.id, *args, **kw)

    async def reply_message(self, msg: agt.Message, *args, **kw):
        return await self._send_coro(
            msg.chat.id,
            msg.reply(*args, **kw)
        )

    async def edit_message(self, msg: agt.Message, *args, **kw):
        return await self._send_coro(
            msg.chat.id,
            msg.edit_text(*args, **kw)
        )
