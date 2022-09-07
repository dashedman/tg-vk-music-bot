# standart libs
import asyncio
import sqlite3
import time
import re
import argparse
import json
import sys
import os
import io
import html
import ssl

from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from configparser import ConfigParser
from pprint import pprint, pformat
from collections import namedtuple, deque
from copy import deepcopy

from functools import partial
from random import randint

# eternal libs
from aiogram import types
from aiogram.dispatcher import webhook
from aiogram.dispatcher.filters import Text
from aiogram.utils import exceptions
from aiohttp import web

# vk_api...
from h11 import RemoteProtocolError

# from vkwave.client import AIOHTTPClient
# from vkwave.api import API, BotSyncSingleToken, Token
# from vkwave.api.methods.audio import Audio

# ssl generate lib
import requests_async as requests

# internal lib
import ui_constants as uic
import tg_lib
from root.components.telegram import TelegramComponent
from root.components.vk import VkComponent
from tg_lib import DictionaryBomb


# function
# message demon-worker functions

async def get_popular(self.vk.audio, self.database, message):
    # seek music in vk
    current_page = 1
    request = "!popular"

    if request in MUSICLIST_CACHE and current_page * MUSIC_LIST_LENGTH <= len(MUSICLIST_CACHE[request][1]):
        musiclist = get_cache(MUSICLIST_CACHE, request, current_page)[(current_page - 1) * 9:current_page * 9]
        NEXT_PAGE_FLAG = True
        if len(musiclist) < MUSIC_LIST_LENGTH or current_page == 11: NEXT_PAGE_FLAG = False
    else:
        while True:
            try:
                loop = asyncio.get_running_loop()
                res_generator = await loop.run_in_executor(None, self.vk.audio.get_popular_iter)
                musiclist, NEXT_PAGE_FLAG = await tg_lib.get_music_list(res_generator, current_page, MUSIC_LIST_LENGTH)
            except ConnectionError:
                await asyncio.sleep(1)
            else:

                break
        if NEXT_PAGE_FLAG: asyncio.create_task(caching_list(self.vk.audio, request))

    # construct inline keyboard for list
    return uic.get_inline_keyboard(musiclist, request, NEXT_PAGE_FLAG, current_page)


async def get_new_songs(self.vk.audio, self.database, message):
    # seek music in vk
    current_page = 1
    request = "!new_songs"

    if request in MUSICLIST_CACHE and current_page * MUSIC_LIST_LENGTH <= len(MUSICLIST_CACHE[request][1]):
        musiclist = get_cache(MUSICLIST_CACHE, request, current_page)[(current_page - 1) * 9:current_page * 9]
        NEXT_PAGE_FLAG = True
        if len(musiclist) < MUSIC_LIST_LENGTH or current_page == 11: NEXT_PAGE_FLAG = False
    else:
        while True:
            try:
                loop = asyncio.get_running_loop()
                res_generator = await loop.run_in_executor(None, self.vk.audio.get_news_iter)
                musiclist, NEXT_PAGE_FLAG = await tg_lib.get_music_list(res_generator, current_page, MUSIC_LIST_LENGTH)
            except ConnectionError:
                await asyncio.sleep(1)
            else:
                break
        if NEXT_PAGE_FLAG: asyncio.create_task(caching_list(self.vk.audio, request))

    # construct inline keyboard for list
    return uic.get_inline_keyboard(musiclist, request, NEXT_PAGE_FLAG, current_page)


async def get_state():
    with open(self.config['bot']['state_filename'], "r", encoding='utf-8') as f:
        return f.read()


async def set_state(new_state):
    with open(self.config['bot']['state_filename'], "w", encoding='utf-8') as f:
        return f.write(new_state)


@dataclass
class VkHandler:
    session: 'VkApi'
    audio: 'VkAudio'


@dataclass
class TelegramHandler:
    bot: 'Bot'
    dispatcher: 'Dispatcher'


class MusicBot(BaseBot):
    def __init__(self, constants, config, logger):
        self.constants = constants
        self.config = config
        self.logger = logger

        self.logger.info(f"Initializing...")

        # self.database loading
        self.logger.info(f"Database loading...")
        self.database = sqlite3.connect(self.config['data-base']['host'])
        # all_mode table
        with self.database:
            cur = self.database.cursor()
            cur.execute(
                """CREATE TABLE IF NOT EXISTS chats
                (id TEXT PRIMARY KEY,
                mode BOOL NOT NULL,
                ad_counter INT NOT NULL DEFAULT 25)""")

            cur.execute(
                """CREATE TABLE IF NOT EXISTS audios
                (
                    id          TEXT PRIMARY KEY,
                    telegram_id TEXT UNIQUE NOT NULL,
                    audio_size  REAL        NOT NULL
                )""")

            # PRINTING TABLES
            # db_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            # self.logger.info("TABLES:")
            # for table in db_cursor.fetchall():
            #    self.logger.info(f"\t{table[0]}")

        # COMPONENTS
        self.vk = VkComponent(self.config['vk'], self.logger)
        self.telegram = TelegramComponent(self.config['telegram'], self.logger)

        self.demons = []

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

    async def on_startup(self, app):
        if self.config['network'].getboolean('is_webhook'):
            webhook = await self.telegram.bot.get_webhook_info()
            self.logger.info("Old webhook:\n" + pformat(webhook.to_python()))

            self.logger.info(f"Setting Webhook...")
            webhook_url = f"https://{self.config['network']['domen']}:{self.config['network']['domen_port']}{self.config['network']['path']}"

            if self.config['ssl'].getboolean('self'):
                with open(os.path.join(self.config['ssl']['dir'], self.config['ssl']['cert_filename']), "rb") as f:
                    await self.telegram.bot.set_webhook(
                        webhook_url,
                        certificate=f
                    )
            else:
                await self.telegram.bot.set_webhook(webhook_url)

            webhook = await self.telegram.bot.get_webhook_info()
            self.logger.info("New webhook:\n" + pformat(webhook.to_python()))
            if webhook.url != webhook_url:
                self.logger.info(f"WebHook wasn't set!")
                Exception("Webhook wasn't set!")
            self.logger.info(f"WebHook successful set!")

        self.logger.info("Starting demons...")
        self.demons.extend([
            # asyncio.create_task(reauth_demon(self.vk.session, True))
        ])
        uic.set_signature((await self.telegram.bot.me).mention)

        # await vk_api.audio.set_user_id((await vk_api.users.get(return_raw_response = True))['response'][0]['id'])
        # await vk_api.audio.set_client_session(vk_client)

    async def on_shutdown(self, app):
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
            app = webhook.get_new_configured_app(dispatcher=self.telegram.dispatcher, path=self.config['network']['path'])
            app.on_startup.append(self.on_startup)
            app.on_shutdown.append(self.on_shutdown)

            context = None
            if self.config['ssl'].getboolean('self'):
                # create ssl for webhook
                self.create_self_signed_cert()
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
                dispatcher=dispatcher,
                on_startup=on_startup,
                on_shutdown=on_shutdown,
                skip_updates=True
            )

    def initialize_handlers(self):
        dispatcher = self.telegram.dispatcher
        # ============= HANDLERS ============
        @dispatcher.message_handler(commands=["start"])
        @dispatcher.message_handler(Text(equals=uic.KEYBOARD_COMMANDS["start"]))
        async def start_handler(message: types.Message):
            # processing command /start
            # send keyboard to user
            await message.reply(f"Keyboard for...", reply_markup=uic.MAIN_KEYBOARD)

        @dispatcher.message_handler(commands=["find", "f"])
        async def find_handler(message: types.Message):
            # processing command /find
            # send finder inline keyboard to user
            command, expression = message.get_full_command()

            if len(expression.encode("utf-8")) == 0:
                await message.reply(uic.EMPTY)
                return
            if len(expression.encode("utf-8")) > 59:
                await message.reply(uic.TOO_BIG)
                return
            keyboard = await seek_music(self.vk.audio, self.database, message, expression)
            if keyboard is None:
                await message.reply(uic.NOT_FOUND)
            else:
                await message.reply(uic.FINDED, reply_markup=keyboard, disable_web_page_preview=True)

        @dispatcher.message_handler(commands=["review", "r"], commands_ignore_caption=False,
                                    content_types=types.ContentType.ANY)
        async def review_handler(message: types.Message):
            # processing command /find
            # get streams from db
            # and
            # construct keyboard
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

        @dispatcher.message_handler(commands=["popular", "chart"])
        @dispatcher.message_handler(FastText(equals=uic.KEYBOARD_COMMANDS["popular"]))
        async def chart_handler(message: types.Message):
            # processing command /popular
            # send popular inline keyboard to user
            keyboard = await get_popular(self.vk.audio, self.database, message)
            if keyboard is None:
                await message.reply(uic.NOT_FOUND)
            else:
                await message.reply(uic.FINDED, reply_markup=keyboard, disable_web_page_preview=True)

        @dispatcher.message_handler(commands=["new_songs", "novelties"])
        @dispatcher.message_handler(FastText(equals=uic.KEYBOARD_COMMANDS["new_songs"]))
        async def new_songs_handler(message: types.Message):
            # processing command /new_songs
            # send news inline keyboard to user
            keyboard = await get_new_songs(self.vk.audio, self.database, message)
            if keyboard is None:
                await message.reply(uic.NOT_FOUND)
            else:
                await message.reply(uic.FINDED, reply_markup=keyboard, disable_web_page_preview=True)

        @dispatcher.message_handler(commands=["help"])
        @dispatcher.message_handler(FastText(equals=uic.KEYBOARD_COMMANDS["help"]))
        async def help_handler(message: types.Message):
            # processing command /help
            await message.reply(uic.HELP_TEXT)

        @dispatcher.message_handler(commands=["about"])
        @dispatcher.message_handler(FastText(equals=uic.KEYBOARD_COMMANDS["about"]))
        async def about_handler(message: types.Message):
            # processing command /about
            await message.reply(uic.ABOUT_TEXT)

        @dispatcher.message_handler(commands=["get_state"])
        @dispatcher.message_handler(FastText(equals=uic.KEYBOARD_COMMANDS["get_state"]))
        async def about_handler(message: types.Message):
            # processing command /get_state
            await message.reply(await get_state())

        @dispatcher.message_handler(commands=["settings"])
        @dispatcher.message_handler(FastText(equals=uic.KEYBOARD_COMMANDS["settings"]))
        async def settings_handler(message: types.Message):
            # processing command /settings
            tmp_settings_keyboard = deepcopy(uic.SETTINGS_KEYBOARD)
            tmp_settings_keyboard.append([IKB(text=(
                '🙈 Listen only to commands'
                if tg_lib.all_mode_check(self.database, message.chat.id)
                else '🐵 Listen to all message'
            ))])
            await message.reply(
                uic.SETTINGS,
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=tmp_settings_keyboard,
                    resize_keyboard=True, one_time_keyboard=True, selective=True)
            )

        admin_filter = AdminFilter()
        private_chat_filter = ChatTypeFilter(types.chat.ChatType.PRIVATE)

        @dispatcher.message_handler(admin_filter, commands=["all_mode_on"])
        @dispatcher.message_handler(admin_filter, FastText(equals=uic.KEYBOARD_COMMANDS["all_mode_on"]))
        @dispatcher.message_handler(private_chat_filter, commands=["all_mode_on"])
        @dispatcher.message_handler(private_chat_filter, FastText(equals=uic.KEYBOARD_COMMANDS["all_mode_on"]))
        async def all_mode_on_handler(message: types.Message):
            # processing command /about
            tg_lib.all_mode_on(self.database, message.chat.id)

            tmp_settings_keyboard = deepcopy(uic.SETTINGS_KEYBOARD)
            tmp_settings_keyboard.append([IKB(text=(
                '🙈 Listen only to commands'
                if tg_lib.all_mode_check(self.database, message.chat.id)
                else '🐵 Listen to all message'
            ))])
            await message.reply(
                uic.MODE_ON,
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=tmp_settings_keyboard,
                    resize_keyboard=True, one_time_keyboard=True, selective=True))

        @dispatcher.message_handler(admin_filter, commands=["all_mode_off"])
        @dispatcher.message_handler(admin_filter, FastText(equals=uic.KEYBOARD_COMMANDS["all_mode_off"]))
        @dispatcher.message_handler(private_chat_filter, commands=["all_mode_off"])
        @dispatcher.message_handler(private_chat_filter, FastText(equals=uic.KEYBOARD_COMMANDS["all_mode_off"]))
        async def all_mode_off_handler(message: types.Message):
            # processing command /about
            tg_lib.all_mode_off(self.database, message.chat.id)

            tmp_settings_keyboard = deepcopy(uic.SETTINGS_KEYBOARD)
            tmp_settings_keyboard.append([IKB(text=(
                '🙈 Listen only to commands'
                if tg_lib.all_mode_check(self.database, message.chat.id)
                else '🐵 Listen to all message'
            ))])
            await message.reply(
                uic.MODE_OFF,
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=tmp_settings_keyboard,
                    resize_keyboard=True, one_time_keyboard=True, selective=True))

        @dispatcher.message_handler(commands=["all_mode_on", "all_mode_off"])
        @dispatcher.message_handler(
            FastText(equals=[
                uic.KEYBOARD_COMMANDS["all_mode_on"],
                uic.KEYBOARD_COMMANDS["all_mode_off"]
            ]))
        async def no_admin_handler(message: types.Message):
            await message.reply(uic.NO_ACCESS)

        dashboard_filter = IDFilter(chat_id=self.config['telegram']['dashboard'])

        @dispatcher.message_handler(dashboard_filter, commands=["vipinfo"])
        async def send_info(message: types.Message):
            await message.answer("```\n" + pformat(message.to_python()) + "```", parse_mode="markdown")

        @dispatcher.message_handler(dashboard_filter, commands=["viphelp"])
        async def viphelp_handler(message: types.Message):
            # processing command /viphelp
            await message.reply(uic.VIPHELP_TEXT)

        @dispatcher.message_handler(dashboard_filter, commands=["rep"], commands_ignore_caption=False,
                                    content_types=types.ContentType.ANY)
        async def rep_handler(message: types.Message):
            # processing command /del caption
            # get streamers from db
            # and
            # construct keyboard
            command, args = message.get_full_command()
            args = args.split()
            chat_id = args[0]
            rep_msg = ' '.join(args[1:])

            try:
                await self.telegram.bot.send_message(chat_id, rep_msg)
            except BotBlocked:
                await message.answer("Bot blocked by user(")
            except ChatNotFound:
                await message.answer("Invalid ID")
            except UserDeactivated:
                await message.answer("User is deactivated")
            except:
                await message.reply(uic.ERROR)
                raise
            else:
                await message.reply(uic.SENDED)

        @dispatcher.message_handler(dashboard_filter, commands=["cache"])
        async def cache_handler(message: types.Message):
            # processing command /cache
            str_list = ""
            ntime = time.time()
            for it, request in enumerate(MUSICLIST_CACHE):
                str_list += f"{it}. [{request}]: len={len(MUSICLIST_CACHE[request][1])}\ttime={int(MUSICLIST_CACHE[request][0].timer - ntime)}\n"
            await message.reply(f"Music list cashe({len(MUSICLIST_CACHE)})\n" + str_list)

        @dispatcher.message_handler(dashboard_filter, commands=["set_state"])
        async def set_state_handler(message: types.Message):
            # processing command /set_state
            command, expression = message.get_full_command()
            if await set_state(expression):
                await message.reply(uic.SETTED)
            else:
                await message.reply(uic.WRONG)

        @dispatcher.message_handler(dashboard_filter, commands=["log"])
        async def log_handler(message: types.Message):
            # processing command /log
            await message.chat.do('upload_document')
            await message.answer_document(document=types.InputFile('bot.log'))

        @dispatcher.message_handler(dashboard_filter, commands=["logs"])
        async def all_logs_handler(message: types.Message):
            # processing command /logs
            await message.chat.do('upload_document')
            group = types.MediaGroup()
            # main log
            group.attach_document(types.InputFile('bot.log'), 'Last Logs')
            # other logs
            for i in range(1, self.config['logging'].getint('backup_length') + 1):
                try:
                    group.attach_document(types.InputFile(f'bot.log.{i}'))
                except FileNotFoundError:
                    break
            await message.answer_media_group(media=group)

        @dispatcher.message_handler(dashboard_filter, commands=["err"])
        async def all_err_handler(message: types.Message):
            # processing command /logs
            raise Exception("My Err C:")

        @dispatcher.message_handler(ContentTypeFilter(["text"]),
                                    lambda message: tg_lib.all_mode_check(self.database, message.chat.id) and message.text[
                                        0] != '/')
        async def text_handler(message: types.Message):
            message.text = f"/f{(await self.telegram.bot.me).mention} {message.text}"
            await find_handler(message)

        @dispatcher.callback_query_handler()
        async def button_handler(callback_query: types.CallbackQuery):
            args = callback_query.data.split("@")
            command, data = args[0], args[1:]

            if command == 'pass':
                return

            if command == 'd':  # download audio
                full_audio_id = data[0] + '_' + data[1]

                await callback_query.message.chat.do('upload_document')
                while full_audio_id in IS_DOWNLOAD:
                    await asyncio.sleep(0.07)

                # cached flag
                CACHED = True
                # check audio in old loads
                if audio_data := tg_lib.db_get_audio(self.database, full_audio_id):
                    telegram_id, audio_size = audio_data
                    # send id from old audio in telegram
                    if audio_size == 0:
                        # delete if file is empty
                        tg_lib.db_del_audio(self.database, full_audio_id)
                        CACHED = False
                    else:
                        try:
                            await callback_query.message.answer_audio(
                                audio=telegram_id,
                                caption=f'{audio_size:.2f} MB (cached)\n{uic.SIGNATURE}',
                                parse_mode='html'
                            )
                        except:
                            # if telegram clear his cache files or file is broken
                            tg_lib.db_del_audio(self.database, full_audio_id)
                else:

                    CACHED = False

                if not CACHED:
                    # set lock on downloading this track
                    IS_DOWNLOAD.add(full_audio_id)

                    owner_id, audio_id = data
                    loop = asyncio.get_running_loop()
                    new_audio = await loop.run_in_executor(None, self.vk.audio.get_audio_by_id, owner_id, audio_id)

                    # download audio

                    response = await requests.head(new_audio['url'])

                    audio_size = int(response.headers.get('content-length', 0)) / MEGABYTE_SIZE

                    if audio_size >= 50:
                        duration = time.gmtime(new_audio['duration'])
                        await callback_query.message.answer(
                            uic.unescape(
                                f"{new_audio['artist']} - {new_audio['title']} "
                                f"({duration.tm_min}:{duration.tm_sec:02})\n"
                                f"This audio file size is too large :c"
                            )
                        )
                        IS_DOWNLOAD.discard(full_audio_id)
                        return

                    elif audio_size == 0:
                        duration = time.gmtime(new_audio['duration'])
                        await callback_query.message.answer(
                            uic.unescape(
                                f"{new_audio['artist']} - {new_audio['title']} "
                                f"({duration.tm_min}:{duration.tm_sec:02})\n"
                                f"This audio file is empty :c"
                            )
                        )
                        IS_DOWNLOAD.discard(full_audio_id)
                        self.logger.warning(f'Empty file\n{pformat(new_audio)}')
                        return


                    while True:
                        try:
                            response = await requests.get(new_audio['url'])

                        except RemoteProtocolError:
                            await self.telegram.bot.send_message(self.config['telegram']['dashboard'], "Cicle Load")
                            await asyncio.sleep(0)
                        else:

                            break

                    # send new audio file
                    response = await callback_query.message.answer_audio(
                        audio=types.InputFile(
                            io.BytesIO(response.content),
                            filename=f"{new_audio['artist'][:32]}_{new_audio['title'][:32]}.mp3"
                        ),
                        title=uic.unescape(new_audio['title']),
                        performer=uic.unescape(new_audio['artist']),
                        caption=f'{audio_size:.2f} MB\n{uic.SIGNATURE}',
                        duration=new_audio['duration'],
                        parse_mode='html'
                    )

                    # save new audio in db
                    tg_lib.db_put_audio(self.database,
                                        full_audio_id,
                                        response['audio']['file_id'],
                                        audio_size)

                    IS_DOWNLOAD.discard(full_audio_id)

            if command == 'e':

                request = data[0]
                current_page = int(data[1])  # or ad_id for ad

                if request in MUSICLIST_CACHE and current_page * MUSIC_LIST_LENGTH <= len(MUSICLIST_CACHE[request][1]):
                    musiclist = get_cache(MUSICLIST_CACHE, request, current_page)[(current_page - 1) * 9:current_page * 9]
                    NEXT_PAGE_FLAG = True
                    if len(musiclist) < MUSIC_LIST_LENGTH or current_page == 11:
                        NEXT_PAGE_FLAG = False
                else:
                    while True:
                        try:
                            if request == "!popular":
                                res_generator = self.vk.audio.get_popular_iter(offset=current_page * MUSIC_LIST_LENGTH)
                            elif request == "!new_songs":
                                res_generator = self.vk.audio.get_news_iter(offset=(current_page - 1) * MUSIC_LIST_LENGTH)
                            else:
                                res_generator = self.vk.audio.search_iter(request, offset=(current_page - 1) * MUSIC_LIST_LENGTH)

                            musiclist, NEXT_PAGE_FLAG = await tg_lib.get_music_list(res_generator, current_page,
                                                                                    MUSIC_LIST_LENGTH)
                        except ConnectionError:
                            await asyncio.sleep(1)
                        else:
                            break
                    if NEXT_PAGE_FLAG: asyncio.create_task(caching_list(self.vk.audio, request))

                # construct inline keyboard for list
                inline_keyboard = uic.get_inline_keyboard(musiclist, request, NEXT_PAGE_FLAG, current_page)

                # send answer
                await callback_query.message.edit_reply_markup(reply_markup=inline_keyboard)

            if command == 'h':
                request = data[0]
                current_page = int(data[1])  # or ad_id if request == '!ad'

                inline_keyboard = uic.get_hide_keyboard(request, current_page)
                await callback_query.message.edit_reply_markup(reply_markup=inline_keyboard)

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
                self.logger.exception(f"\n\n{'=' * 20} HandlerError[{error}] {'=' * 20}\n{pformat(info.to_python())}\n")  #
                await self.telegram.bot.send_message(
                    self.config['telegram']['dashboard'],
                    f'{uic.ERROR}\n{error}')
            return True



if __name__ == "__main__":
    # if main then start bot
    start_bot()
