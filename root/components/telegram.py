
# telegram api
import html
import time

from aiogram import Bot, Dispatcher, types
from aiogram.types.inline_keyboard import InlineKeyboardMarkup, InlineKeyboardButton as IKB
from aiogram.types.reply_keyboard import ReplyKeyboardMarkup, KeyboardButton as RKB

from aiogram.dispatcher.filters import AdminFilter, Text, ContentTypeFilter, ChatTypeFilter
from aiogram.dispatcher.filters.builtin import IDFilter
from aiogram.dispatcher.handler import CancelHandler, current_handler

from aiogram.dispatcher import webhook
from aiogram.utils import markdown as md
from aiogram.utils.executor import start_polling, start_webhook
from aiogram.utils import exceptions
from aiogram.utils.exceptions import BotBlocked, ChatNotFound, UserDeactivated
from aiogram.contrib.fsm_storage.memory import MemoryStorage

import soundcloud_lib as sc

from root.utils import ThrottlingMiddleware
from root.components.base import AbstractComponent


class TelegramComponent(AbstractComponent):
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger

        self.logger.info("Telegram autentification...")
        self.bot = Bot(token=self.config['token'])
        self.storage = MemoryStorage()
        self.dispatcher = Dispatcher(self.bot, storage=self.storage)

        middleware = ThrottlingMiddleware(throttling_rate_limit=1.5, silence_cooldown=30)
        self.dispatcher.middleware.setup(middleware)

    @staticmethod
    def get_inline_keyboard(tracklist: list['sc.Track']):
        inline_keyboard = []
        for track in tracklist:
            duration = time.gmtime(track.duration)
            inline_keyboard.append([
                IKB(
                    text=html.unescape(f"{track['artist']} - {track['title']} ({duration.tm_min}:{duration.tm_sec:02})".replace("$#", "&#")),
                    callback_data=f"d@{track['owner_id']}@{track['id']}",
                )
            ])
        return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
