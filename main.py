#standart libs
import asyncio
import sqlite3
import time
import re
import argparse
import json
import sys
import os
import html
import ssl
import logging

from logging.handlers import RotatingFileHandler
from configparser import ConfigParser
from pprint import pprint, pformat
from collections import namedtuple, deque
from copy import deepcopy

from functools import partial
from random import randint

#eternal libs
from aiohttp import web
#telegram api
from aiogram import Bot, Dispatcher, types
from aiogram.types.inline_keyboard import InlineKeyboardMarkup, InlineKeyboardButton as IKB
from aiogram.types.reply_keyboard import ReplyKeyboardMarkup, KeyboardButton as RKB
from aiogram.dispatcher import DEFAULT_RATE_LIMIT
from aiogram.dispatcher.filters import AdminFilter, Text, ContentTypeFilter, ChatTypeFilter
from aiogram.dispatcher.filters.builtin import IDFilter
from aiogram.dispatcher.handler import CancelHandler, current_handler
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher import webhook
from aiogram.utils import markdown as md
from aiogram.utils.executor import start_polling, start_webhook
from aiogram.utils import exceptions
from aiogram.contrib.fsm_storage.memory import MemoryStorage

#vk_api...
from vk_api import VkApi
from async_extend import AsyncVkApi, AsyncVkAudio

#from vkwave.client import AIOHTTPClient
#from vkwave.api import API, BotSyncSingleToken, Token
#from vkwave.api.methods.audio import Audio

#ssl generate lib
from OpenSSL import crypto
import requests_async as requests

#internal lib
import ui_constants as uic
import tg_lib
from tg_lib import DictionaryBomb



#configs
if not os.path.exists("config.ini"):
    print(uic.NO_CONFIG_MESSAGE)
    exit()

CONFIGS = ConfigParser()
CONFIGS.read("config.ini")

#logining
file_log = RotatingFileHandler(
    "bot.log",
    mode='a',
    maxBytes=20480,
    backupCount=CONFIGS['logging'].getint('backup_length'))
console_out = logging.StreamHandler()

logging.basicConfig(
    handlers=(file_log, console_out),
    format='[%(asctime)s | %(levelname)s] %(name)s: %(message)s',
    datefmt='%a %b %d %H:%M:%S %Y',
    level=CONFIGS['logging'].getint('level'))
logging.getLogger('aiohttp.access').setLevel(logging.WARNING)
logging.getLogger('aiohttp.client').setLevel(logging.WARNING)
logging.getLogger('aiohttp.internal').setLevel(logging.WARNING)
logging.getLogger('aiohttp.server').setLevel(logging.WARNING)
logging.getLogger('aiohttp.web').setLevel(logging.WARNING)
logging.getLogger('aiohttp.websocket').setLevel(logging.WARNING)

LOGGER = logging.getLogger("bot")

#constants
ALIVE = False
MEGABYTE_SIZE = 1<<20
MUSIC_LIST_LENGTH = 9
MUSICLIST_CACHE= {}
TRACK_CACHE= {}
IS_DOWNLOAD = set()
IS_REAUTH = False
CONNECT_COUNTER = 0

#classes
class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, database, throttling_rate_limit=DEFAULT_RATE_LIMIT, silence_cooldown=0, key_prefix='antiflood_'):
        self.rate_limit = throttling_rate_limit
        self.silence_cooldown = silence_cooldown
        self.prefix = key_prefix
        self.database = database

        super(ThrottlingMiddleware, self).__init__()

    def set_database(database):
        self.database = database

    async def on_process_message(self, message: types.Message, data: dict):
        """
        This handler is called when dispatcher receives a message
        :param message:
        """

        # Get current handler and dispatcher from context
        handler = current_handler.get()
        dispatcher = Dispatcher.get_current()

        # Cheking to outdated
        if time.time() - message.date.timestamp() > 5*60:
            LOGGER.info("Skip outdated command!")

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
            await self.message_throttled(message, t)    # Execute action
            raise CancelHandler()                       # Cancel current handler

        LOGGER.info(f"Message {message.text or message.caption or '!non text!'}")

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

        LOGGER.info(f"Callback {callback_query.data}")

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
            await callback_query.answer(f"Don't flood. Please wait for {throttled.rate} sec.", show_alert = False)
        elif throttled.exceeded_count >= 2:
            pass

class FastText(Text):
    def __init__(self,
                 equals = None,
                 contains = None,
                 startswith = None,
                 endswith = None,
                 ignore_case=False):

        super().__init__(equals, contains, startswith, endswith, ignore_case)
        if self.ignore_case:
            _pre_process_func = (lambda s: str(s).lower())
        else:
            _pre_process_func = str

        self.equals = set(map(_pre_process_func, self.equals))              if self.equals is not None      else None
        self.contains = tuple(map(_pre_process_func, self.contains))        if self.contains is not None    else None
        self.startswith = tuple(map(_pre_process_func, self.startswith))    if self.startswith is not None  else None
        self.endswith = tuple(map(_pre_process_func, self.endswith))        if self.endswith is not None    else None

    async def check(self, obj): #obj: types.Union[Message, CallbackQuery, types.InlineQuery, types.Poll]
        if isinstance(obj, types.Message):
            text = obj.text or obj.caption or ''
            if not text and obj.poll:
                text = obj.poll.question
        elif isinstance(obj, types.CallbackQuery):
            text = obj.data
        elif isinstance(obj, types.InlineQuery):
            text = obj.query
        elif isinstance(obj, types.Poll):
            text = obj.question
        else:
            return False

        if self.ignore_case:
            text = text.lower()

        # now check
        if self.equals is not None:
            return text in self.equals

        if self.contains is not None:
            return all(map(text.__contains__, self.contains))

        if self.startswith is not None:
            return any(map(text.startswith, self.startswith))

        if self.endswith is not None:
            return any(map(text.endswith, self.endswith))

        return False

#functions

#self-ssl
def create_self_signed_cert():
    k = crypto.PKey()
    k.generate_key(crypto.TYPE_RSA, 1024)   #  размер может быть 2048, 4196

    #  Создание сертификата
    cert = crypto.X509()
    cert.get_subject().C = "RU"   #  указываем свои данные
    cert.get_subject().ST = "Saint-Petersburg"
    cert.get_subject().L = "Saint-Petersburg"   #  указываем свои данные
    cert.get_subject().O = "pff"   #  указываем свои данные
    cert.get_subject().CN = CONFIGS['network']['domen']   #  указываем свои данные
    cert.set_serial_number(1)
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(365*24*60*60)   #  срок "жизни" сертификата
    cert.set_issuer(cert.get_subject())
    cert.set_pubkey(k)
    cert.sign(k, 'SHA256')

    with open(os.path.join(CONFIGS['ssl']['dir'], CONFIGS['ssl']['cert_filename']), "w") as f:
        f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert).decode("ascii"))

    with open(os.path.join(CONFIGS['ssl']['dir'], CONFIGS['ssl']['key_filename']), "w") as f:
        f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k).decode("ascii"))

    return crypto.dump_certificate(crypto.FILETYPE_PEM, cert).decode("ascii")

#cache functions
def get_cache(cache, key, current_page):
    cache[key][0].replant(time.time()+60*5)
    return cache[key][1]

async def caching_list(vk_audio, request):
    if request in MUSICLIST_CACHE: return
    #bomb on 5 minutes
    bomb = DictionaryBomb(MUSICLIST_CACHE, request, time.time()+60*5)

    if request == "!popular":
        generator = vk_audio.get_popular_iter()
    elif request == "!new_songs":
        generator = vk_audio.get_news_iter()
    else:
        generator = vk_audio.search_iter(request)

    musiclist = []
    MUSICLIST_CACHE[request] = (bomb, musiclist)

    musiclist.append(await generator.__anext__())
    for i in range(98):
        try:
            next_track = await generator.__anext__()
            if next_track == musiclist[0]:break
            musiclist.append(next_track)
        except StopAsyncIteration:
            break

    asyncio.create_task(bomb.plant())


#message demon-worker functions
async def seek_music(vk_audio, database, message, request):
    #seek music in vk
    current_page = 1

    if request in MUSICLIST_CACHE and current_page*MUSIC_LIST_LENGTH <= len(MUSICLIST_CACHE[request][1]):
        musiclist = get_cache(MUSICLIST_CACHE, request, current_page)[(current_page-1)*9:current_page*9]
        NEXT_PAGE_FLAG = True
        if len(musiclist)<MUSIC_LIST_LENGTH or current_page == 11: NEXT_PAGE_FLAG = False

    else:
        while True:
            try:
                res_generator = vk_audio.search_iter(request)
                musiclist, NEXT_PAGE_FLAG = await tg_lib.get_music_list(res_generator, current_page, MUSIC_LIST_LENGTH)
            except ConnectionError:
                asyncio.sleep(1)
            else:
                break

        if not musiclist:
            return None

        if NEXT_PAGE_FLAG: asyncio.create_task(caching_list(vk_audio, request))
    #construct inline keyboard for list
    return uic.get_inline_keyboard(musiclist, request, NEXT_PAGE_FLAG, current_page)

async def get_popular(vk_audio, database, message):
    #seek music in vk
    current_page = 1
    request = "!popular"

    if request in MUSICLIST_CACHE and current_page*MUSIC_LIST_LENGTH <= len(MUSICLIST_CACHE[request][1]):
        musiclist = get_cache(MUSICLIST_CACHE, request, current_page)[(current_page-1)*9:current_page*9]
        NEXT_PAGE_FLAG = True
        if len(musiclist)<MUSIC_LIST_LENGTH or current_page == 11: NEXT_PAGE_FLAG = False
    else:
        while True:
            try:
                res_generator = vk_audio.get_popular_iter()
                musiclist, NEXT_PAGE_FLAG = await tg_lib.get_music_list(res_generator, current_page, MUSIC_LIST_LENGTH)
            except ConnectionError:
                asyncio.sleep(1)
            else:

                break
        if NEXT_PAGE_FLAG: asyncio.create_task(caching_list(vk_audio, request))

    #construct inline keyboard for list
    return uic.get_inline_keyboard(musiclist, request, NEXT_PAGE_FLAG, current_page)

async def get_new_songs(vk_audio, database, message):
    #seek music in vk
    current_page = 1
    request = "!new_songs"

    if request in MUSICLIST_CACHE and current_page*MUSIC_LIST_LENGTH <= len(MUSICLIST_CACHE[request][1]):
        musiclist = get_cache(MUSICLIST_CACHE, request, current_page)[(current_page-1)*9:current_page*9]
        NEXT_PAGE_FLAG = True
        if len(musiclist)<MUSIC_LIST_LENGTH or current_page == 11: NEXT_PAGE_FLAG = False
    else:
        while True:
            try:
                res_generator = vk_audio.get_news_iter()
                musiclist, NEXT_PAGE_FLAG = await tg_lib.get_music_list(res_generator, current_page, MUSIC_LIST_LENGTH)
            except ConnectionError:
                asyncio.sleep(1)
            else:
                break
        if NEXT_PAGE_FLAG: asyncio.create_task(caching_list(vk_audio, request))

    #construct inline keyboard for list
    return uic.get_inline_keyboard(musiclist, request, NEXT_PAGE_FLAG, current_page)

async def get_state():
    with open(CONFIGS['bot']['state_filename'], "r", encoding='utf-8') as f:
        return f.read()

async def set_state(new_state):
    with open(CONFIGS['bot']['state_filename'], "w", encoding='utf-8') as f:
        return f.write(new_state)


#start func
def start_bot():
    LOGGER.info(f"Hi!")
    loop = asyncio.get_event_loop()

    #database loading
    LOGGER.info(f"Database loading...")
    database = sqlite3.connect(CONFIGS['data-base']['host'])

    #all_mode table
    with database:
        cur = database.cursor()
        cur.execute(
            """CREATE TABLE IF NOT EXISTS chats
            (id TEXT PRIMARY KEY,
            mode BOOL NOT NULL)""")

        # PRINTING TABLES
        #db_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        #LOGGER.info("TABLES:")
        #for table in db_cursor.fetchall():
        #    LOGGER.info(f"\t{table[0]}")

    #autetifications in vk
    LOGGER.info(f"Vk autentification...")
    vk_session = AsyncVkApi(
        login=CONFIGS['vk']['login'],
        password=CONFIGS['vk']['password'],
        auth_handler=tg_lib.auth_handler,
        loop = loop
    )
    vk_session.sync_auth()
    vk_audio = AsyncVkAudio(vk_session)
    #vk_client = AIOHTTPClient()
    #vk_token = BotSyncSingleToken(CONFIGS['vk']['token'])
    #vk_api_session = API(vk_token, vk_client)
    #vk_api = vk_api_session.get_context()
    #vk_audio = vk_api.audio

    #create bot
    bot = Bot(token=CONFIGS['telegram']['token'], loop=loop)
    storage = MemoryStorage()
    dispatcher = Dispatcher(bot, storage=storage)

    middleware = ThrottlingMiddleware(database, throttling_rate_limit=1.5, silence_cooldown=30)
    dispatcher.middleware.setup(middleware)

    #============= HANDLERS ============
    @dispatcher.message_handler(commands=["start"])
    @dispatcher.message_handler(FastText(equals=uic.KEYBOARD_COMMANDS["start"]))
    async def start_handler(message: types.Message):
        #processing command /start
        #send keyboard to user
        await message.reply(f"Keyboard for...", reply_markup=uic.MAIN_KEYBOARD)

    @dispatcher.message_handler(commands=["find", "f"])
    async def find_handler(message: types.Message):
        #processing command /find
        #send finder inline keyboard to user
        command, expression = message.get_full_command()

        if len(expression.encode("utf-8")) == 0:
            await message.reply(uic.EMPTY)
            return
        if len(expression.encode("utf-8")) > 59:
            await message.reply(uic.TOO_BIG)
            return
        keyboard = await seek_music(vk_audio, database, message, expression)
        if keyboard is None:
            await message.reply(uic.NOT_FOUND)
        else:
            await message.reply(uic.FINDED, reply_markup=keyboard, disable_web_page_preview=True)

    @dispatcher.message_handler(commands=["review", "r"], commands_ignore_caption=False, content_types=types.ContentType.ANY)
    async def review_handler(message: types.Message):
        #processing command /find
        #get streams from db
        #and
        #construct keyboard
        command, msg_for_dev = message.get_full_command()
        if(len(msg_for_dev) == 0):
            await message.reply(uic.EMPTY)
            return

        if(len(msg_for_dev) < 3):
            await message.reply(uic.TOO_SMALL)
            return

        try:
            if(message.reply_to_message is not None):
                await message.reply_to_message.forward(CONFIGS['telegram']['dashboard'])
            await message.forward(CONFIGS['telegram']['dashboard'])
            await bot.send_message(CONFIGS['telegram']['dashboard'], uic.build_review_info(message), parse_mode="html")

            await message.answer(uic.SENDED)
        except exceptions.BadRequest:
            await message.answer(uic.FORWARD_ERROR)
        except:
            await message.answer(uic.ERROR)
            raise
        return

    @dispatcher.message_handler(commands=["popular", "chart"])
    @dispatcher.message_handler(FastText(equals=uic.KEYBOARD_COMMANDS["popular"]))
    async def chart_handler(message: types.Message):
        #processing command /popular
        #send popular inline keyboard to user
        keyboard = await get_popular(vk_audio, database, message)
        if keyboard is None:
            await message.reply(uic.NOT_FOUND)
        else:
            await message.reply(uic.FINDED, reply_markup=keyboard, disable_web_page_preview=True)

    @dispatcher.message_handler(commands=["new_songs", "novelties"])
    @dispatcher.message_handler(FastText(equals=uic.KEYBOARD_COMMANDS["new_songs"]))
    async def new_songs_handler(message: types.Message):
        #processing command /new_songs
        #send news inline keyboard to user
        keyboard = await get_new_songs(vk_audio, database, message)
        if keyboard is None:
            await message.reply(uic.NOT_FOUND)
        else:
            await message.reply(uic.FINDED, reply_markup=keyboard, disable_web_page_preview=True)

    @dispatcher.message_handler(commands=["help"])
    @dispatcher.message_handler(FastText(equals=uic.KEYBOARD_COMMANDS["help"]))
    async def help_handler(message: types.Message):
        #processing command /help
        await message.reply(uic.HELP_TEXT)

    @dispatcher.message_handler(commands=["about"])
    @dispatcher.message_handler(FastText(equals=uic.KEYBOARD_COMMANDS["about"]))
    async def about_handler(message: types.Message):
        #processing command /about
        await message.reply(uic.ABOUT_TEXT)

    @dispatcher.message_handler(commands=["get_state"])
    @dispatcher.message_handler(FastText(equals=uic.KEYBOARD_COMMANDS["get_state"]))
    async def about_handler(message: types.Message):
        #processing command /get_state
        await message.reply(await get_state())

    @dispatcher.message_handler(commands=["settings"])
    @dispatcher.message_handler(FastText(equals=uic.KEYBOARD_COMMANDS["settings"]))
    async def settings_handler(message: types.Message):
        #processing command /settings
        tmp_settings_keyboard = deepcopy(uic.SETTINGS_KEYBOARD)
        tmp_settings_keyboard.append([ IKB( text=(
            '🙈 Listen only to commands'
            if tg_lib.all_mode_check(database, message.chat.id)
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
        #processing command /about
        tg_lib.all_mode_on(database, message.chat.id)

        tmp_settings_keyboard = deepcopy(uic.SETTINGS_KEYBOARD)
        tmp_settings_keyboard.append([ IKB( text=(
            '🙈 Listen only to commands'
            if tg_lib.all_mode_check(database, message.chat.id)
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
        #processing command /about
        tg_lib.all_mode_off(database, message.chat.id)

        tmp_settings_keyboard = deepcopy(uic.SETTINGS_KEYBOARD)
        tmp_settings_keyboard.append([ IKB( text=(
            '🙈 Listen only to commands'
            if tg_lib.all_mode_check(database, message.chat.id)
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

    dashboard_filter = IDFilter(chat_id=CONFIGS['telegram']['dashboard'])
    @dispatcher.message_handler(dashboard_filter, commands=["vipinfo"])
    async def send_info(message: types.Message):
        await message.answer("```\n"+pformat(message.to_python())+"```", parse_mode="markdown")

    @dispatcher.message_handler(dashboard_filter, commands=["viphelp"])
    async def viphelp_handler(message: types.Message):
        #processing command /viphelp
        await message.reply(uic.VIPHELP_TEXT)

    @dispatcher.message_handler(dashboard_filter, commands=["rep"], commands_ignore_caption=False, content_types=types.ContentType.ANY)
    async def rep_handler(message: types.Message):
        #processing command /del caption
        #get streamers from db
        #and
        #construct keyboard
        command, args = message.get_full_command()
        args = args.split()
        chat_id = args[0]
        rep_msg = ' '.join(args[1:])

        try:
            await bot.send_message(chat_id, rep_msg)
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
        #processing command /cache
        str_list=""
        ntime = time.time()
        for it, request in enumerate(MUSICLIST_CACHE):
            str_list += f"{it}. [{request}]: len={len(MUSICLIST_CACHE[request][1])}\ttime={int(MUSICLIST_CACHE[request][0].timer-ntime)}\n"
        await message.reply(f"Music list cashe({len(MUSICLIST_CACHE)})\n"+str_list)

    @dispatcher.message_handler(dashboard_filter, commands=["set_state"])
    async def set_state_handler(message: types.Message):
        #processing command /set_state
        command, expression = message.get_full_command()
        if await set_state(expression):
            await message.reply(uic.SETTED)
        else:
            await message.reply(uic.WRONG)

    @dispatcher.message_handler(dashboard_filter, commands=["log"])
    async def log_handler(message: types.Message):
        #processing command /log
        await message.chat.do('upload_document')
        await message.answer_document(document=types.InputFile('bot.log'))

    @dispatcher.message_handler(dashboard_filter, commands=["logs"])
    async def all_logs_handler(message: types.Message):
        #processing command /logs
        await message.chat.do('upload_document')
        group = types.MediaGroup()
        #main log
        group.attach_document(types.InputFile('bot.log'), 'Last Logs')
        #other logs
        for i in range(1, CONFIGS['logging'].getint('backup_length')+1):
            try:
                group.attach_document(types.InputFile(f'bot.log.{i}'))
            except FileNotFoundError:
                break
        await message.answer_media_group(media=group)

    @dispatcher.message_handler(dashboard_filter, commands=["err"])
    async def all_err_handler(message: types.Message):
        #processing command /logs
        raise Exception("My Err C:")

    @dispatcher.message_handler(ContentTypeFilter(["text"]), lambda message: tg_lib.all_mode_check(database, message.chat.id) and message.text[0] != '/')
    async def text_handler(message: types.Message):
        message.text = f"/f{(await bot.me).mention} {message.text}"
        await find_handler(message)

    @dispatcher.callback_query_handler()
    async def button_handler(callback_query: types.CallbackQuery):
        args = callback_query.data.split("@")
        command, data = args[0], args[1:]


        if command == 'pass': return

        if command == 'd': # download audio
            full_audio_id = data[0]+'_'+data[1]

            await callback_query.message.chat.do('upload_document')
            while full_audio_id in IS_DOWNLOAD:

                await asyncio.sleep(0.07)

            CACHED = True

            #check audio in old loads
            if audio_data := tg_lib.db_get_audio(database, full_audio_id):

                telegram_id, audio_size = audio_data
                #send id from old audio in telegram
                try:

                    await callback_query.message.answer_audio(
                        audio = telegram_id,
                        caption=f'{audio_size:.2f} MB (cached)\n{uic.SIGNATURE}',
                        parse_mode='html'
                    )

                except:
                    #if telegram clear his cache files

                    tg_lib.db_del_audio(database, full_audio_id)
            else:

                CACHED = False

            if not CACHED:

                IS_DOWNLOAD.add(full_audio_id)


                owner_id, audio_id = data
                new_audio = await vk_audio.get_audio_by_id(owner_id, audio_id)

                #download audio

                response = await requests.head(new_audio['URL'])

                audio_size = int(response.headers.get('content-length', 0)) / MEGABYTE_SIZE
                if audio_size >= 50:
                    duration = time.gmtime(new_audio['DURATION'])
                    await callback_query.message.answer(
                        uic.unescape(f"{new_audio['PERFORMER']} - {new_audio['TITLE']} ({duration.tm_min}:{duration.tm_sec:02})\nThis audio file size is too large :c")
                    )
                    IS_DOWNLOAD.discard(full_audio_id)
                    return


                while True:
                    try:

                        response = await requests.get(new_audio['URL'])

                    except RemoteProtocolError:
                        await bot.send_message(CONFIGS['telegram']['dashboard'], "Cicle Load")
                        await asyncio.sleep(0)
                    else:

                        break


                #send new audio file

                response = await callback_query.message.answer_audio(
                    audio = response.content,
                    title = uic.unescape(new_audio['TITLE']),
                    performer = uic.unescape(new_audio['PERFORMER']),
                    caption=f'{audio_size:.2f} MB\n{uic.SIGNATURE}',
                    parse_mode='html'
                )


                #save new audio in db
                tg_lib.db_put_audio( database, \
                                      full_audio_id, \
                                      response['audio']['file_id'],
                                      audio_size)

                IS_DOWNLOAD.discard(full_audio_id)

        if command == 'e':

            request = data[0]
            current_page = int(data[1])# or ad_id for ad

            if request in MUSICLIST_CACHE and current_page*MUSIC_LIST_LENGTH <= len(MUSICLIST_CACHE[request][1]):
                musiclist = get_cache(MUSICLIST_CACHE, request, current_page)[(current_page-1)*9:current_page*9]
                NEXT_PAGE_FLAG = True
                if len(musiclist)<MUSIC_LIST_LENGTH or current_page == 11: NEXT_PAGE_FLAG = False
            else:
                while True:
                    try:
                        if request == "!popular":
                            res_generator = vk_audio.get_popular_iter(offset=current_page*MUSIC_LIST_LENGTH )
                        elif request == "!new_songs":
                            res_generator = vk_audio.get_news_iter(offset=(current_page-1)*MUSIC_LIST_LENGTH )
                        else:
                            res_generator = vk_audio.search_iter(request, offset=(current_page-1)*MUSIC_LIST_LENGTH )

                        musiclist, NEXT_PAGE_FLAG = await tg_lib.get_music_list(res_generator, current_page, MUSIC_LIST_LENGTH)
                    except ConnectionError:
                        asyncio.sleep(1)
                    else:
                        break
                if NEXT_PAGE_FLAG: asyncio.create_task(caching_list(vk_audio, request))

            #construct inline keyboard for list
            inline_keyboard = uic.get_inline_keyboard( musiclist, request, NEXT_PAGE_FLAG, current_page)

            #send answer
            await callback_query.message.edit_reply_markup(reply_markup = inline_keyboard)

        if command == 'h':
            request = data[0]
            current_page = int(data[1])#or ad_id if request == '!ad'

            inline_keyboard = uic.get_hide_keyboard(request, current_page)
            await callback_query.message.edit_reply_markup(reply_markup = inline_keyboard)

    @dispatcher.errors_handler()
    async def error_handler(info, error):
        if type(error) in (
            exceptions.MessageNotModified,
            exceptions.InvalidQueryID
        ) or str(error) in (
            "Replied message not found",
        ):
            LOGGER.warning(f"{'='*3} HandlerError[{error}] {'='*3}")
        else:
            await bot.send_message(CONFIGS['telegram']['dashboard'], uic.ERROR)
            LOGGER.exception(f"\n\n{'='*20} HandlerError[{error}] {'='*20}\n{pformat(info.to_python())}\n")#error
        return True

    #end handlers
    demons = []

    async def send_message(user_id: int, text: str, disable_notification: bool = False) -> bool:
        """
        Safe messages sender

        :param user_id:
        :param text:
        :param disable_notification:
        :return:
        """
        try:
            await bot.send_message(user_id, text, disable_notification=disable_notification)
        except exceptions.BotBlocked:
            log.error(f"Target [ID:{user_id}]: blocked by user")
        except exceptions.ChatNotFound:
            log.error(f"Target [ID:{user_id}]: invalid chat ID")
        except exceptions.RetryAfter as e:
            log.error(f"Target [ID:{user_id}]: Flood limit is exceeded. Sleep {e.timeout} seconds.")
            await asyncio.sleep(e.timeout)
            return await send_message(user_id, text)  # Recursive call
        except exceptions.UserDeactivated:
            log.error(f"Target [ID:{user_id}]: user is deactivated")
        except exceptions.TelegramAPIError:
            log.exception(f"Target [ID:{user_id}]: failed")
        except exceptions.BadRequest:
            log.exception(f"Target [ID:{user_id}]: bad request")
        else:
            return True
        return False

    async def on_startup(app):
        if CONFIGS['network'].getboolean('is_webhook'):
            webhook = await bot.get_webhook_info()
            LOGGER.info("Old webhook:\n"+pformat(webhook.to_python()))

            LOGGER.info(f"Setting Webhook...")
            webhook_url = f"https://{CONFIGS['network']['domen']}:{CONFIGS['network']['domen_port']}{CONFIGS['network']['path']}"

            if CONFIGS['ssl'].getboolean('self'):
                with open(os.path.join(CONFIGS['ssl']['dir'], CONFIGS['ssl']['cert_filename']), "rb") as f:
                    await bot.set_webhook(
                        webhook_url,
                        certificate=f
                    )
            else:
                await bot.set_webhook(webhook_url)

            webhook = await bot.get_webhook_info()
            LOGGER.info("New webhook:\n"+pformat(webhook.to_python()))
            if webhook.url != webhook_url:
                LOGGER.info(f"WebHook wasn't setted!")
                Exception("Webhook wasn't setted!")
            LOGGER.info(f"WebHook succesful setted!")

        LOGGER.info("Starting demons...")
        demons.extend([
            #asyncio.create_task(reauth_demon(vk_session, True))
        ])
        uic.set_signature((await bot.me).mention)

        #await vk_api.audio.set_user_id((await vk_api.users.get(return_raw_response = True))['response'][0]['id'])
        #await vk_api.audio.set_client_session(vk_client)

    async def on_shutdown(app):
        LOGGER.info("Killing demons...")
        for demon in demons:
            demon.cancel()
        LOGGER.info("All demons was killed.")

        await vk_audio.wait()

        await bot.delete_webhook()
        await dispatcher.storage.close()
        await dispatcher.storage.wait_closed()


    if CONFIGS['network'].getboolean('is_webhook'):
        app = webhook.get_new_configured_app(dispatcher=dispatcher, path=CONFIGS['network']['path'])
        app.on_startup.append(on_startup)
        app.on_shutdown.append(on_shutdown)

        if CONFIGS['ssl'].getboolean('self'):
            #create ssl for webhook
            create_self_signed_cert()
            context = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
            context.load_cert_chain(
                os.path.join(CONFIGS['ssl']['dir'], CONFIGS['ssl']['cert_filename']),
                keyfile=os.path.join(CONFIGS['ssl']['dir'], CONFIGS['ssl']['key_filename'])
            )

        web.run_app(
            app,
            host=CONFIGS['network']['host'],
            port=CONFIGS['network'].getint('port'),
            ssl_context=context if CONFIGS['ssl'].getboolean('self') else None
        )
    else:
        start_polling(
            dispatcher=dispatcher,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            skip_updates=True
        )

if __name__ == "__main__":
    #if main then start bot
    start_bot()
