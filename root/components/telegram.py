
# telegram api
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

from root.utils import ThrottlingMiddleware
from root.components.base import AbstractComponent


class TelegramComponent(AbstractComponent):
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger

        self.logger.info("Telegram autentification...")
        self.bot = Bot(token=self.config['telegram']['token'])
        self.storage = MemoryStorage()
        self.dispatcher = Dispatcher(self.bot, storage=self.storage)

        middleware = ThrottlingMiddleware(throttling_rate_limit=1.5, silence_cooldown=30)
        self.dispatcher.middleware.setup(middleware)
