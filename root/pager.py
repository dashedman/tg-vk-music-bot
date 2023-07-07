import asyncio
import io
import logging
import time
from typing import AsyncIterable

import aiogram.types as agt
import aiogram.utils.exceptions
from aiogram.types import ChatActions

import aitertools
import root.ui_constants as uic
from root.commander import CallbackCommander, CommandId
from root.models import Track


class PagersManager:
    def __init__(self, commander: CallbackCommander):
        self.commander = commander

    def create_pager(self, message, tracks_gen, target):
        return Pager(
            self,
            message,
            tracks_gen,
            target=target,
            lifetime=600
        )


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
        self._target = target

        self._current_page = -1
        self._pages: list[tuple[
            CommandId,
            list[tuple[CommandId, Track]]
        ]] = []
        self._current_tracks: list[CommandId] = []
        self._current_page_buttons: list[CommandId] = []

        self.logger = logging.getLogger('Pager')

        self.start(user_message)

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
        await self._message.delete()

    def reload_deadline(self):
        self._deadline = time.time() + self._lifetime

    def in_lifetime(self):
        return time.time() < self._deadline

    async def service(self, user_message: 'agt.Message', pager_size: int = 5):
        success = await self.prepare_first_page(user_message)
        if not success:
            await user_message.reply(uic.NOT_FOUND)
            await asyncio.sleep(30)
            await self.clear()
            return

        while self._alive and self.in_lifetime():
            if len(self._pages) < pager_size and success:
                success = await self.prepare_next_page()

            await asyncio.sleep(1)

        await self.clear()

    def construct_page_keyboard(self):
        inline_keyboard = []
        _, page = self._pages[self._current_page]
        # set track buttons
        for get_track_com, track in page:
            duration = time.gmtime(track.duration)
            inline_keyboard.append([
                agt.InlineKeyboardButton(
                    text=f"{track.performer} - {track.title} ({duration.tm_min}:{duration.tm_sec:02})",
                    callback_data=str(get_track_com),
                )
            ])
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
        return agt.InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

    async def prepare_first_page(self, user_message: 'agt.Message') -> bool:
        tracks = await self.get_tracks_for_page()
        if not tracks:
            return False

        self._current_page = 0
        page_command = self._manager.commander.create_command(
            self.switch_page,
            self._current_page
        )
        self._pages.append((page_command, tracks))

        keyboard = self.construct_page_keyboard()
        self._message = await user_message.reply(
            uic.FINDED, reply_markup=keyboard, disable_web_page_preview=True
        )
        return True

    async def prepare_next_page(self) -> bool:
        tracks = await self.get_tracks_for_page()
        if not tracks:
            return False

        page_command = self._manager.commander.create_command(
            self.switch_page,
            len(self._pages)
        )
        self._pages.append((page_command, tracks))

        keyboard = self.construct_page_keyboard()
        try:
            await self._message.edit_text(
                uic.FINDED, reply_markup=keyboard, disable_web_page_preview=True
            )
        except aiogram.utils.exceptions.MessageNotModified:
            pass
        return True

    async def get_tracks_for_page(self, page_size: int = 10) -> list[(CommandId, Track)]:
        tracks = []
        async for t in aitertools.islice(self._tracks_gen, page_size):
            send_track_command_id = self._manager.commander.create_command(
                self.send_track, t)
            tracks.append((send_track_command_id, t))
        return tracks

    # CALLBACKS
    async def send_track(self, callback_query: agt.CallbackQuery, track: Track):
        self.reload_deadline()

        message, track_data, _ = await asyncio.gather(
            callback_query.message.answer(
                uic.starting_download(track.title, track.performer),
            ),
            track.load_audio(),
            callback_query.message.answer_chat_action(ChatActions.UPLOAD_DOCUMENT)
        )

        await asyncio.gather(
            message.delete(),
            callback_query.message.answer_audio(
                audio=agt.InputFile(
                    io.BytesIO(track_data),
                    filename=f"{track.performer[:32]}_{track.title[:32]}.mp3",

                ),
                title=track.title,
                performer=track.performer,
                caption=uic.SIGNATURE,
                duration=track.duration,
                parse_mode='html',
            )
        )

    async def switch_page(self, _: agt.CallbackQuery, page_number: int):
        self.logger.info('Switch page to %s', page_number)
        self.reload_deadline()
        self._current_page = page_number

        keyboard = self.construct_page_keyboard()
        await self._message.edit_text(
            uic.FINDED, reply_markup=keyboard, disable_web_page_preview=True
        )
