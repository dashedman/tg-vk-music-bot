
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
from root.models import Track

from root.utils import ThrottlingMiddleware
from root.sections.base import AbstractSection


class TelegramHandler:
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
    def get_inline_keyboard(commands_to_tracks: dict[int, 'Track']):
        inline_keyboard = []
        for command_id, track in commands_to_tracks:
            duration = time.gmtime(track.duration)
            inline_keyboard.append([
                IKB(
                    text=html.unescape(f"{track.performer} - {track.title} ({duration.tm_min}:{duration.tm_sec:02})".replace("$#", "&#")),
                    callback_data=str(command_id),
                )
            ])
        return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
