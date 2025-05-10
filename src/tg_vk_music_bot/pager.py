import asyncio
import logging
import time
from collections import defaultdict
from typing import AsyncIterable

import aiogram.types as agt
from aiogram.exceptions import TelegramAPIError

import aitertools
import tg_vk_music_bot
import tg_vk_music_bot.ui_constants as uic
from tg_vk_music_bot.commander import CommandId
from tg_vk_music_bot.models import Track, Album


class PagersManager:
    def __init__(
            self,
            bot: 'tg_vk_music_bot.MusicBot',
    ):
        self.bot = bot
        self.pager_registry: dict[str, list[Pager]] = defaultdict(list)

    @property
    def commander(self):
        return self.bot.callback_commander

    @property
    def cache(self):
        return self.bot.tracks_cache

    @property
    def constants(self):
        return self.bot.constants

    @property
    def loads_demon(self):
        return self.bot.loads_demon

    @property
    def tg_bot(self):
        return self.bot.telegram

    @property
    def db_engine(self):
        return self.bot.db_engine

    def create_pager(self, message, tracks_gen, target):
        return Pager(
            self,
            message,
            tracks_gen,
            target,
            lifetime=self.constants.PAGER_LIFETIME
        )

    def create_albums_pager(self, message, albums_gen, target):
        return AlbumsPager(
            self,
            message,
            albums_gen,
            target,
            lifetime=self.constants.PAGER_LIFETIME
        )

    def register_pager(self, pager: 'Pager'):
        self.pager_registry[pager.target].append(pager)

    def delete_pager(self, pager: 'Pager'):
        self.pager_registry[pager.target].remove(pager)

    def get_by_target(self, target: str) -> 'Pager | None':
        target_pagers = self.pager_registry[target]
        if target_pagers:
            return target_pagers[0]
        return None


class Pager:
    _message: 'agt.Message' = None

    def __init__(
            self,
            pagers_manager: PagersManager,
            user_message: 'agt.Message',
            tracks_gen: AsyncIterable[Track],
            target: str,
            lifetime: int = 300
    ):
        self._alive = False
        self._lifetime = lifetime
        self._deadline = 0

        self._manager = pagers_manager
        self._tracks_gen = tracks_gen
        self.target = target

        self._current_page = -1
        self._pages: list[tuple[
            CommandId,
            list[tuple[CommandId, Track]]
        ]] = []

        self.logger = logging.getLogger('Pager')

        self._manager.register_pager(self)

        self.start(user_message)

    @property
    def tg_bot(self):
        return self._manager.tg_bot

    @property
    def db_engine(self):
        return self._manager.db_engine

    def start(self, user_message: 'agt.Message'):
        self.reload_deadline()
        self._alive = True
        asyncio.create_task(self.service(user_message))

    async def clear(self):
        self._alive = False
        for get_page_com, tracks in self._pages:
            for get_track_com, _ in tracks:
                self._manager.commander.delete_command(get_track_com)
            self._manager.commander.delete_command(get_page_com)
        self._manager.delete_pager(self)
        await self.tg_bot.delete_message(self._message)

    def reload_deadline(self):
        self._deadline = time.time() + self._lifetime

    def in_lifetime(self):
        return time.time() < self._deadline

    async def service(self, user_message: 'agt.Message', pager_size: int = 5):
        await self._manager.bot.vk.limiter.wait()
        success = await self.prepare_first_page(user_message)
        if not success:
            self._message = await self.tg_bot.reply_message(user_message, uic.NOT_FOUND)
            await asyncio.sleep(30)
            await self.clear()
            return

        while self._alive and self.in_lifetime():
            if len(self._pages) < pager_size and success:
                await self._manager.bot.vk.limiter.wait()
                success = await self.prepare_next_page()

                if success and (1 + len(self._pages)) % 2 == 0:
                    await self.edit_keyboard()
                elif not success and (1 + len(self._pages)) % 2 != 0:
                    # not success, last update of keyboard
                    await self.edit_keyboard()
            await asyncio.sleep(0)
        await self.clear()

    async def construct_page_keyboard(self):
        inline_keyboard = []
        await self._add_tracks_buttons(inline_keyboard)
        self._add_page_buttons(inline_keyboard)
        return agt.InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

    async def _add_tracks_buttons(self, inline_keyboard):
        _, page = self._pages[self._current_page]

        track_ids_for_page = [t.get_id() for _, t in page]
        tracks_in_cache = set(
            await self._manager.cache.check_cache(track_ids_for_page)
        )
        # set track buttons
        for get_track_com, track in page:
            duration = time.gmtime(track.duration)
            inline_keyboard.append([
                agt.InlineKeyboardButton(
                    text=uic.build_track_button_name(
                        track.performer,
                        track.title,
                        duration,
                        track.get_id() in tracks_in_cache
                    ),
                    callback_data=str(get_track_com),
                )
            ])

    def _add_page_buttons(self, inline_keyboard):
        # set page buttons
        page_btns = []
        for i, (get_page_com, _) in enumerate(self._pages):
            if i == self._current_page:
                btn_text = f'[{self._current_page + 1}]'
                callback_data = self._manager.commander.DO_NOTHING
            else:
                btn_text = str(i + 1)
                callback_data = get_page_com

            page_btns.append(
                agt.InlineKeyboardButton(
                    text=btn_text,
                    callback_data=str(callback_data),
                )
            )
        inline_keyboard.append(page_btns)

    async def prepare_first_page(self, user_message: 'agt.Message') -> bool:
        entities = await self.get_entities_for_page()
        if not entities:
            return False

        self._current_page = 0
        page_command = self._manager.commander.create_command(
            self.switch_page,
            self._current_page
        )
        self._pages.append((page_command, entities))

        keyboard = await self.construct_page_keyboard()
        self._message = await self.tg_bot.reply_message(
            user_message,
            self.finded_message(),
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        return True

    async def prepare_next_page(self) -> bool:
        entities = await self.get_entities_for_page()
        if not entities:
            return False

        page_command = self._manager.commander.create_command(
            self.switch_page,
            len(self._pages)
        )
        self._pages.append((page_command, entities))
        return True

    async def edit_keyboard(self):
        keyboard = await self.construct_page_keyboard()
        try:
            await self.tg_bot.edit_message(
                self._message,
                self.finded_message(),
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
        except TelegramAPIError as e:
            self.logger.error('Catch while edit keyboard:', exc_info=e)

    async def get_entities_for_page(self, page_size: int = 10) -> list[(CommandId, Track)]:
        tracks = []
        async for t in aitertools.islice(self._tracks_gen, page_size):
            send_track_command_id = self._manager.commander.create_command(
                self.send_track, t)
            tracks.append((send_track_command_id, t))
        return tracks

    # CALLBACKS
    async def send_track(self, callback_query: agt.CallbackQuery, track: Track):
        self.reload_deadline()
        await self._manager.cache.send_track(track, callback_query.message.chat)

    async def switch_page(self, _: agt.CallbackQuery, page_number: int):
        self.logger.info('Switch page to %s', page_number)
        self.reload_deadline()
        self._current_page = page_number

        keyboard = await self.construct_page_keyboard()
        await self.tg_bot.edit_message(
            self._message,
            self.finded_message(),
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

    def finded_message(self):
        return uic.FINDED


class AlbumsPager(Pager):
    _pages: list[tuple[
        CommandId,
        list[tuple[CommandId, Album]]
    ]]

    def __init__(
            self,
            pagers_manager: PagersManager,
            user_message: 'agt.Message',
            albums_gen: AsyncIterable[Track],
            target: str,
            lifetime: int = 300
    ):
        self.tracks_by_album: dict[str, list[tuple[CommandId, Track]]] = {}
        super().__init__(
            pagers_manager,
            user_message,
            albums_gen,
            target,
            lifetime,
        )

    async def clear(self):
        for album in self.tracks_by_album.values():
            for get_track_com, _ in album:
                self._manager.commander.delete_command(get_track_com)
        await super().clear()

    def finded_message(self):
        return uic.FINDED_ALBUMS

    async def get_entities_for_page(self, page_size: int = 10) -> list[(CommandId, Album)]:
        albums = []
        async for t in aitertools.islice(self._tracks_gen, page_size):
            send_track_command_id = self._manager.commander.create_command(
                self.send_album_list, t)
            albums.append((send_track_command_id, t))
        return albums

    async def construct_page_keyboard(self):
        inline_keyboard = []
        await self._add_albums_buttons(inline_keyboard)
        self._add_page_buttons(inline_keyboard)
        return agt.InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

    async def construct_album_page(self, album: Album):
        inline_keyboard = []
        await self._add_album_tracks_buttons(inline_keyboard, album)
        self._add_control_buttons(inline_keyboard)
        return agt.InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

    async def _add_albums_buttons(self, inline_keyboard):
        _, page = self._pages[self._current_page]

        # set track buttons
        for get_album_com, album in page:
            inline_keyboard.append([
                agt.InlineKeyboardButton(
                    text=uic.build_album_button_name(
                        album.performer,
                        album.title,
                        album.size,
                        album.plays,
                        album.tracks is not None,
                    ),
                    callback_data=str(get_album_com),
                )
            ])

    async def _add_album_tracks_buttons(self, inline_keyboard, album):
        tracks = self.tracks_by_album.get(album.get_id())
        if tracks is None:
            await album.load_tracks()
            tracks = []
            for t in album.tracks:
                send_track_command_id = self._manager.commander.create_command(
                    self.send_track, t)
                tracks.append((send_track_command_id, t))
            self.tracks_by_album[album.get_id()] = tracks

        track_ids_for_page = [t.get_id() for _, t in tracks]
        tracks_in_cache = set(
            await self._manager.cache.check_cache(track_ids_for_page)
        )
        # set track buttons
        for get_track_com, track in tracks[:90]:
            duration = time.gmtime(track.duration)
            inline_keyboard.append([
                agt.InlineKeyboardButton(
                    text=uic.build_track_button_name(
                        track.performer,
                        track.title,
                        duration,
                        track.get_id() in tracks_in_cache
                    ),
                    callback_data=str(get_track_com),
                )
            ])

        if len(tracks) > 90:
            inline_keyboard.append([
                agt.InlineKeyboardButton(
                    text=uic.ALBUM_IS_TOO_LONG,
                    callback_data=str(self._manager.commander.DO_NOTHING),
                )
            ])

    def _add_control_buttons(self, inline_keyboard):
        current_page_com, _ = self._pages[self._current_page]
        inline_keyboard.append([
            agt.InlineKeyboardButton(
                text=uic.BACK,
                callback_data=str(current_page_com),
            )
        ])

    async def send_album_list(self, _: agt.CallbackQuery, album: Album):
        self.logger.info('Switch page to Album: %s', album.full_name)
        self.reload_deadline()

        keyboard = await self.construct_album_page(album)
        await self.tg_bot.edit_message(
            self._message,
            self.finded_message(),
            reply_markup=keyboard,
            disable_web_page_preview=True
        )



