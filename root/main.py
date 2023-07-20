# standart libs
import asyncio
import os
import ssl
from copy import deepcopy
from logging import Logger

from pprint import pformat

from gevent.threadpool import ThreadPoolExecutor as GeventPoolExecutor
from aiogram.types import ReplyKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# eternal libs
from aiogram import types
from aiogram.dispatcher import webhook
from aiogram.dispatcher.filters import Text, IDFilter, AdminFilter, ChatTypeFilter, ContentTypeFilter
from aiogram.utils import exceptions
from aiogram.utils.executor import start_polling
from aiogram.types.inline_keyboard import InlineKeyboardButton as IKB
from aiohttp import web

# internal lib

import root.ui_constants as uic

import root.utils.utils as utils
from root import db_models
from root.commander import CallbackCommander
from root.constants import Constants
from root.loads_demon import LoadsDemon
from root.pager import PagersManager
# from root.sections.soundcloud import SoundcloudSection
from root.telegram import TelegramHandler
from root.sections.vk import VkSection
from root.tracks_cache import TracksCache


# from root.sections.yandex_music import YandexMusicSection
# from root.sections.soundcloud import SoundcloudComponent


# function
# message demon-worker functions

# async def get_state():
#     with open(self.config['bot']['state_filename'], "r", encoding='utf-8') as f:
#         return f.read()
#
#
# async def set_state(new_state):
#     with open(self.config['bot']['state_filename'], "w", encoding='utf-8') as f:
#         return f.write(new_state)


class MusicBot:
    signer: 'uic.Signer'

    def __init__(self, config, logger: Logger):
        self.constants = Constants()
        self.config = config
        self.logger = logger

        # self.process_executor = ProcessPoolExecutor()
        # self.thread_executor = ThreadPoolExecutor()
        # self.gevent_executor = GeventPoolExecutor()

        self.logger.info(f"Initializing...")
        self.db_engine = create_async_engine('sqlite+aiosqlite:///../tracks_data_base.db')
        self.callback_commander = CallbackCommander()
        self.tracks_cache = TracksCache(self)
        self.loads_demon = LoadsDemon(self, workers=3)
        self.pagers_manager = PagersManager(self)
        self.demons = []

        # self.database loading
        # self.logger.info(f"Database loading...")
        # self.database = sqlite3.connect(self.config['data-base']['host'])
        # # all_mode table
        # with self.database:
        #     cur = self.database.cursor()
        #     cur.execute(
        #         """CREATE TABLE IF NOT EXISTS chats
        #         (id TEXT PRIMARY KEY,
        #         mode BOOL NOT NULL,
        #         ad_counter INT NOT NULL DEFAULT 25)""")
        #
        #     cur.execute(
        #         """CREATE TABLE IF NOT EXISTS audios
        #         (
        #             id          TEXT PRIMARY KEY,
        #             telegram_id TEXT UNIQUE NOT NULL,
        #             audio_size  REAL        NOT NULL
        #         )""")
        #
        #     # PRINTING TABLES
        #     # db_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        #     # self.logger.info("TABLES:")
        #     # for table in db_cursor.fetchall():
        #     #    self.logger.info(f"\t{table[0]}")

        # COMPONENTS
        self.vk = VkSection(self, self.config['vk'], self.logger)
        # self.soundcloud = SoundcloudSection(self.config['soundcloud'], self.logger)
        # self.youtube = YoutubeComponent(self.config['youtube'], self.logger)
        # self.yandex_music = YandexMusicSection(self.config['yandex_music'], self.logger)
        self.telegram = TelegramHandler(self.config['telegram'], self.logger)

    async def find_tracks_gen(self, query):
        tracks_agen = self.vk.get_tracks_gen(query)
        return tracks_agen

    async def new_tracks_gen(self):
        tracks_agen = self.vk.get_new_songs()
        return tracks_agen

    async def popular_tracks_gen(self):
        tracks_agen = self.vk.get_popular_songs()
        return tracks_agen

    async def find_albums_gen(self, query):
        albums_agen = self.vk.get_albums_gen(query)
        return albums_agen

    async def check_free_mode(self, chat: types.Chat) -> bool:
        async with self.db_engine.connect() as conn:
            return await conn.scalar(
                select(
                    db_models.Chat.is_free_mode
                ).where(
                    db_models.Chat.id == chat.id
                )
            )

    async def change_free_mode(self, chat: types.Chat, new_value: bool):
        async_session = async_sessionmaker(
            self.db_engine,
            expire_on_commit=False
        )

        async with async_session() as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    insert(
                        db_models.Chat
                    ).values({
                        db_models.Chat.id.key: chat.id,
                        db_models.Chat.is_free_mode.key: new_value,
                    }).on_conflict_do_update(
                        index_elements=[db_models.Chat.id.key],
                        set_={db_models.Chat.is_free_mode.key: new_value}
                    )
                )

    async def send_message(self, user_id: int, text: str, disable_notification: bool = False) -> bool:
        """
        Safe messages sender

        :param user_id:
        :param text:
        :param disable_notification:
        :return:
        """
        try:
            await self.telegram.bot.send_message(user_id, text, disable_notification=disable_notification)
        except exceptions.BotBlocked:
            self.logger.error(f"Target [ID:{user_id}]: blocked by user")
        except exceptions.ChatNotFound:
            self.logger.error(f"Target [ID:{user_id}]: invalid chat ID")
        except exceptions.RetryAfter as e:
            self.logger.error(f"Target [ID:{user_id}]: Flood limit is exceeded. Sleep {e.timeout} seconds.")
            await asyncio.sleep(e.timeout)
            return await self.send_message(user_id, text)  # Recursive call
        except exceptions.UserDeactivated:
            self.logger.error(f"Target [ID:{user_id}]: user is deactivated")
        except exceptions.BadRequest:
            self.logger.exception(f"Target [ID:{user_id}]: bad request")
        except exceptions.TelegramAPIError:
            self.logger.exception(f"Target [ID:{user_id}]: failed")
        else:
            return True
        return False

    async def on_startup(self, _):
        if self.config['network'].getboolean('is_webhook'):
            webhook_info = await self.telegram.bot.get_webhook_info()
            self.logger.info("Old webhook:\n" + pformat(webhook_info.to_python()))

            self.logger.info(f"Setting Webhook...")
            webhook_url = f"https://{self.config['network']['domen']}" \
                          f":{self.config['network']['domen_port']}" \
                          f"{self.config['network']['path']}"

            if self.config['ssl'].getboolean('self'):
                with open(os.path.join(self.config['ssl']['dir'], self.config['ssl']['cert_filename']), "rb") as f:
                    await self.telegram.bot.set_webhook(
                        webhook_url,
                        certificate=f
                    )
            else:
                await self.telegram.bot.set_webhook(webhook_url)

            webhook_info = await self.telegram.bot.get_webhook_info()
            self.logger.info("New webhook:\n" + pformat(webhook_info.to_python()))
            if webhook_info.url != webhook_url:
                self.logger.info(f"WebHook wasn't set!")
                Exception("Webhook wasn't set!")
            self.logger.info(f"WebHook successful set!")

        self.logger.info("Starting demons...")
        self.demons.extend([
            asyncio.create_task(self.loads_demon.serve()),
            asyncio.create_task(self.telegram.serve()),
            # asyncio.create_task(reauth_demon(self.vk.session, True))
        ])

        self.signer = uic.Signer()
        self.signer.set_signature((await self.telegram.bot.me).mention)

        # await self.vk.prepare()

        # await vk_api.audio.set_user_id((await vk_api.users.get(return_raw_response = True))['response'][0]['id'])
        # await vk_api.audio.set_client_session(vk_client)

    async def on_shutdown(self, _):
        self.logger.info("Killing demons...")
        for demon in self.demons:
            demon.cancel()
        self.logger.info("All demons was killed.")

        await self.telegram.bot.delete_webhook()
        await self.telegram.dispatcher.storage.close()
        await self.telegram.dispatcher.storage.wait_closed()

    def start(self):
        self.initialize_handlers()

        if self.config['network'].getboolean('is_webhook'):
            app = webhook.get_new_configured_app(
                dispatcher=self.telegram.dispatcher,
                path=self.config['network']['path'],
            )
            app.on_startup.append(self.on_startup)
            app.on_shutdown.append(self.on_shutdown)

            context = None
            if self.config['ssl'].getboolean('self'):
                # create ssl for webhook
                utils.create_self_signed_cert(self.config['network'], self.config['ssl'])
                context = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
                context.load_cert_chain(
                    os.path.join(self.config['ssl']['dir'], self.config['ssl']['cert_filename']),
                    keyfile=os.path.join(self.config['ssl']['dir'], self.config['ssl']['key_filename'])
                )

            web.run_app(
                app,
                host=self.config['network']['host'],
                port=self.config['network'].getint('port'),
                ssl_context=context
            )
        else:
            start_polling(
                dispatcher=self.telegram.dispatcher,
                on_startup=self.on_startup,
                on_shutdown=self.on_shutdown,
                skip_updates=True
            )

    def initialize_handlers(self):
        dispatcher = self.telegram.dispatcher
        dashboard_filter = IDFilter(user_id=self.config['telegram']['dashboard'])
        admin_filter = AdminFilter()
        private_chat_filter = ChatTypeFilter(types.chat.ChatType.PRIVATE)
        # ============= HANDLERS ============

        @dispatcher.message_handler(commands=["start"])
        @dispatcher.message_handler(Text(equals=uic.KEYBOARD_COMMANDS["start"]))
        async def start_handler(message: types.Message):
            # processing command /start
            # send keyboard to user
            await self.telegram.reply_message(message, f"Keyboard for...", reply_markup=uic.MAIN_KEYBOARD)

        @dispatcher.message_handler(commands=["settings"])
        @dispatcher.message_handler(Text(equals=uic.KEYBOARD_COMMANDS["settings"]))
        async def settings_handler(message: types.Message):
            # processing command /settings
            await return_settings(message, uic.SETTINGS)

        @dispatcher.message_handler(admin_filter, commands=["all_mode_on"])
        @dispatcher.message_handler(admin_filter, Text(equals=uic.KEYBOARD_COMMANDS["all_mode_on"]))
        @dispatcher.message_handler(private_chat_filter, commands=["all_mode_on"])
        @dispatcher.message_handler(private_chat_filter, Text(equals=uic.KEYBOARD_COMMANDS["all_mode_on"]))
        async def all_mode_on_handler(message: types.Message):
            # processing command /about
            await self.change_free_mode(message.chat, True)
            await return_settings(message, uic.MODE_ON)

        @dispatcher.message_handler(admin_filter, commands=["all_mode_off"])
        @dispatcher.message_handler(admin_filter, Text(equals=uic.KEYBOARD_COMMANDS["all_mode_off"]))
        @dispatcher.message_handler(private_chat_filter, commands=["all_mode_off"])
        @dispatcher.message_handler(private_chat_filter, Text(equals=uic.KEYBOARD_COMMANDS["all_mode_off"]))
        async def all_mode_off_handler(message: types.Message):
            # processing command /about
            await self.change_free_mode(message.chat, False)
            await return_settings(message, uic.MODE_OFF)

        async def return_settings(message: types.Message, msg_text: str):
            tmp_settings_keyboard = deepcopy(uic.SETTINGS_KEYBOARD)
            tmp_settings_keyboard.append([IKB(text=(
                uic.KEYBOARD_COMMANDS['all_mode_off']
                if await self.check_free_mode(message.chat)
                else uic.KEYBOARD_COMMANDS['all_mode_on']
            ))])
            await self.telegram.reply_message(
                message,
                msg_text,
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=tmp_settings_keyboard,
                    resize_keyboard=True,
                    one_time_keyboard=True,
                    selective=True
                )
            )

        @dispatcher.message_handler(commands=["new_songs", "novelties"])
        @dispatcher.message_handler(Text(equals=uic.KEYBOARD_COMMANDS["new_songs"]))
        async def new_songs_handler(message: types.Message):
            # processing command /new_songs
            # send news inline keyboard to user
            tracks_gen = await self.new_tracks_gen()
            self.pagers_manager.create_pager(message, tracks_gen, uic.KEYBOARD_COMMANDS["new_songs"])

        @dispatcher.message_handler(commands=["popular", "chart"])
        @dispatcher.message_handler(Text(equals=uic.KEYBOARD_COMMANDS["popular"]))
        async def chart_handler(message: types.Message):
            # processing command /popular
            # send popular inline keyboard to user
            tracks_gen = await self.popular_tracks_gen()
            self.pagers_manager.create_pager(message, tracks_gen, uic.KEYBOARD_COMMANDS["popular"])

        @dispatcher.message_handler(commands=["albums", "a"])
        async def albums_handler(message: types.Message):
            # processing command /popular
            # send popular inline keyboard to user
            command, expression = message.get_full_command()

            albums_gen = await self.find_albums_gen(expression)
            self.pagers_manager.create_albums_pager(message, albums_gen, expression)

        @dispatcher.message_handler(commands=["help"])
        @dispatcher.message_handler(Text(equals=uic.KEYBOARD_COMMANDS["help"]))
        async def help_handler(message: types.Message):
            # processing command /help
            await message.reply(uic.HELP_TEXT)

        @dispatcher.message_handler(commands=["about"])
        @dispatcher.message_handler(Text(equals=uic.KEYBOARD_COMMANDS["about"]))
        async def about_handler(message: types.Message):
            # processing command /about
            await message.reply(uic.ABOUT_TEXT)

        @dispatcher.message_handler(commands=["review", "r"],
                                    commands_ignore_caption=False,
                                    content_types=types.ContentType.ANY)
        async def review_handler(message: types.Message):
            command, msg_for_dev = message.get_full_command()
            if len(msg_for_dev) == 0:
                await message.reply(uic.EMPTY)
                return

            if len(msg_for_dev) < 3:
                await message.reply(uic.TOO_SMALL)
                return

            try:
                if message.reply_to_message is not None:
                    await message.reply_to_message.forward(self.config['telegram']['dashboard'])
                await message.forward(self.config['telegram']['dashboard'])
                await self.telegram.bot.send_message(
                    self.config['telegram']['dashboard'],
                    uic.build_review_info(message),
                    parse_mode="html"
                )

                await message.answer(uic.SENDED)
            except exceptions.BadRequest:
                await message.answer(uic.ERROR)
            except Exception:
                await message.answer(uic.ERROR)
                raise
            return

        @dispatcher.message_handler(dashboard_filter, commands=["vipinfo"])
        async def send_info(message: types.Message):
            await message.answer("```\n" + pformat(message.to_python()) + "```", parse_mode="markdown")

        @dispatcher.message_handler(dashboard_filter, commands=["viphelp"])
        async def viphelp_handler(message: types.Message):
            await message.reply(uic.VIPHELP_TEXT)

        @dispatcher.message_handler(dashboard_filter, commands=["err"])
        async def all_err_handler(_: types.Message):
            raise Exception("My Err C:")

        @dispatcher.message_handler(dashboard_filter,
                                    commands=["rep"],
                                    commands_ignore_caption=False,
                                    content_types=types.ContentType.ANY)
        async def rep_handler(message: types.Message):
            command, args_str = message.get_full_command()
            chat_id, rep_msg = args_str.split(maxsplit=1)

            try:
                await self.telegram.bot.send_message(chat_id, rep_msg)
            except exceptions.BotBlocked:
                await message.answer("Bot blocked by user(")
            except exceptions.ChatNotFound:
                await message.answer("Invalid ID")
            except exceptions.UserDeactivated:
                await message.answer("User is deactivated")
            except Exception:
                await message.reply(uic.ERROR)
                raise
            else:
                await message.reply(uic.SENDED)

        @dispatcher.message_handler(Text(startswith='\\'))
        async def ignore_text(_: types.Message):
            pass

        find_commands = {"find", "f"}

        @dispatcher.message_handler(commands=find_commands)
        @dispatcher.message_handler(ContentTypeFilter(["text"]))
        async def find_handler(message: types.Message):
            # processing command /find
            # send finder inline keyboard to user

            command_set = message.get_full_command()
            if command_set:
                command, expression = command_set
                if command[1:] not in find_commands:
                    return
            else:
                if await self.check_free_mode(message.chat):
                    expression = message.text or message.caption
                else:
                    return

            # TODO: if zero length state to find

            tracks_gen = await self.find_tracks_gen(expression)
            self.pagers_manager.create_pager(message, tracks_gen, expression)

        @dispatcher.callback_query_handler()
        async def button_handler(callback_query: types.CallbackQuery):
            await self.callback_commander.execute(callback_query)

        @dispatcher.errors_handler()
        async def error_handler(info, error):
            if type(error) in (
                    exceptions.MessageNotModified,
                    exceptions.InvalidQueryID
            ) or str(error) in (
                    "Replied message not found",
            ):
                self.logger.warning(f"{'=' * 3} HandlerError[{error}] {'=' * 3}")
            else:
                self.logger.exception(f"\n\n{'=' * 20} HandlerError[{error}] {'=' * 20}\n{pformat(info.to_python())}\n")

            return True
