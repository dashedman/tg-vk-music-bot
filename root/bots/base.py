import os
import sqlite3
from dataclasses import dataclass

from OpenSSL import crypto
from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from vk_api import VkApi

from root import tg_lib
from root.audio import VkAudio
from root.main import ThrottlingMiddleware


@dataclass
class VkHandler:
    session: 'VkApi'
    audio: 'VkAudio'


@dataclass
class TelegramHandler:
    bot: 'Bot'
    dispatcher: 'Dispatcher'


class BaseBot:
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

        # autetifications in vk
        self.logger.info("Vk autentification...")
        vk_session = VkApi(
            login=self.config['vk']['login'],
            password=self.config['vk']['password'],
            auth_handler=tg_lib.auth_handler
        )
        vk_session.http.headers['User-agent'] = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:94.0) Gecko/20100101 Firefox/94.0'
        vk_session.auth(token_only=True)

        vk_audio = VkAudio(vk_session)
        self.vk = VkHandler(vk_session, vk_audio)

        # autetifications in tg
        self.logger.info("Telegram autentification...")
        bot = Bot(token=self.config['telegram']['token'])
        storage = MemoryStorage()
        dispatcher = Dispatcher(bot, storage=storage)

        middleware = ThrottlingMiddleware(self.database, throttling_rate_limit=1.5, silence_cooldown=30)
        dispatcher.middleware.setup(middleware)
        self.telegram = TelegramHandler(bot, dispatcher)

    async def seek_music(self, message, request):
        # seek music in vk
        current_page = 1

        if request in MUSICLIST_CACHE and current_page * MUSIC_LIST_LENGTH <= len(MUSICLIST_CACHE[request][1]):
            musiclist = get_cache(MUSICLIST_CACHE, request, current_page)[(current_page - 1) * 9:current_page * 9]
            NEXT_PAGE_FLAG = True
            if len(musiclist) < MUSIC_LIST_LENGTH or current_page == 11: NEXT_PAGE_FLAG = False

        else:
            while True:
                try:
                    res_generator = self.vk.audio.search_iter(request)
                    musiclist, NEXT_PAGE_FLAG = await tg_lib.get_music_list(res_generator, current_page, MUSIC_LIST_LENGTH)
                except ConnectionError:
                    await asyncio.sleep(1)
                else:
                    break

            if not musiclist:
                return None

            if NEXT_PAGE_FLAG:
                asyncio.create_task(caching_list(self.vk.audio, request))
        # construct inline keyboard for list
        return uic.get_inline_keyboard(musiclist, request, NEXT_PAGE_FLAG, current_page)
