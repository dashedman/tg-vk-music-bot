import logging
import time

from aiogram import types, Dispatcher
from aiogram.dispatcher import DEFAULT_RATE_LIMIT
from aiogram.dispatcher.handler import current_handler, CancelHandler
from aiogram.dispatcher.middlewares import BaseMiddleware


# classes
from aiogram.utils import exceptions


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, throttling_rate_limit=DEFAULT_RATE_LIMIT, silence_cooldown=0, key_prefix='antiflood_'):
        self.rate_limit = throttling_rate_limit
        self.silence_cooldown = silence_cooldown
        self.prefix = key_prefix
        self.logger = logging.getLogger('Throttle')

        super(ThrottlingMiddleware, self).__init__()

    async def on_process_message(self, message: types.Message, data: dict):
        """
        This handler is called when dispatcher receives a message
        :param message:
        """

        # Get current handler and dispatcher from context
        handler = current_handler.get()
        dispatcher = Dispatcher.get_current()

        # Cheking to outdated
        if time.time() - message.date.timestamp() > 5 * 60:
            self.logger.info("Skip outdated command!")
            raise CancelHandler()

        # If handler was configured, get rate limit and key from handler
        if handler:
            limit = getattr(handler, 'throttling_rate_limit', self.rate_limit)
            key = getattr(handler, 'throttling_key', f"{self.prefix}_{handler.__name__}")
        else:
            limit = self.rate_limit
            key = f"{self.prefix}_message"

        # Use Dispatcher.throttle method.
        try:
            await dispatcher.throttle(key, rate=limit)
        except exceptions.Throttled as t:
            await self.message_throttled(message, t)  # Execute action
            raise CancelHandler()  # Cancel current handler

        self.logger.info(f"Message {message.text or message.caption or '!non text!'}")

    async def message_throttled(self, message: types.Message, throttled: exceptions.Throttled):
        """
        Notify user only on first exceed and notify about unlocking only on last exceed

        :param message:
        :param throttled:
        """
        handler = current_handler.get()
        dispatcher = Dispatcher.get_current()
        if handler:
            key = getattr(handler, 'throttling_key', f"{self.prefix}_{handler.__name__}")
        else:
            key = f"{self.prefix}_message"

        # Prevent flooding
        if throttled.exceeded_count == 2:
            await message.reply(f"Don't flood.\nSilence for {throttled.rate} sec.")
        elif throttled.exceeded_count >= 2:
            pass

    async def on_process_callback_query(self, callback_query: types.CallbackQuery, data: dict):
        """
        This handler is called when dispatcher receives a callback_query

        :param callback_query:
        """
        # Get current handler
        handler = current_handler.get()

        # Get dispatcher from context
        dispatcher = Dispatcher.get_current()
        # If handler was configured, get rate limit and key from handler
        if handler:
            limit = getattr(handler, 'throttling_rate_limit', self.rate_limit)
            key = getattr(handler, 'throttling_key', f"{self.prefix}_{handler.__name__}_{callback_query.data}")
        else:
            limit = self.rate_limit
            key = f"{self.prefix}_callback_query_{callback_query.data}"

        # Use Dispatcher.throttle method.
        try:
            await dispatcher.throttle(key, rate=limit)
        except exceptions.Throttled as t:
            # Execute action
            await self.callback_query_throttled(callback_query, t)

            # Cancel current handler
            raise CancelHandler()

        self.logger.info(f"Callback {callback_query.data}")

    async def callback_query_throttled(self, callback_query: types.CallbackQuery, throttled: exceptions.Throttled):
        """
        Notify user only on first exceed and notify about unlocking only on last exceed

        :param callback_query:
        :param throttled:
        """
        handler = current_handler.get()
        dispatcher = Dispatcher.get_current()
        if handler:
            key = getattr(handler, 'throttling_key', f"{self.prefix}_{handler.__name__}_{callback_query.data}")
        else:
            key = f"{self.prefix}_callback_query_{callback_query.data}"

        # Prevent flooding
        if throttled.exceeded_count == 2:
            await callback_query.answer(f"Don't flood. Please wait for {throttled.rate} sec.", show_alert=False)
        elif throttled.exceeded_count >= 2:
            pass