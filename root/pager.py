import asyncio
import io
import time
from typing import AsyncIterable

import aiogram.types as agt
import aiogram.utils.markdown as agmd

import aitertools
import root.ui_constants as uic
from root.commander import CallbackCommander
from root.models import Track


class PagersManager:
    def __init__(self, commander: CallbackCommander):
        self.commander = commander

    def create_pager(self, message, tracks_gen):
        return Pager(
            self,
            message,
            tracks_gen,
            lifetime=600
        )


class Pager:
    _message: 'agt.Message' = None

    def __init__(
            self,
            pagers_manager: PagersManager,
            user_message: 'agt.Message',
            tracks_gen: AsyncIterable[Track],
            lifetime: int = 300
    ):
        self._alive = False
        self._lifetime = lifetime
        self._deadline = 0

        self._manager = pagers_manager
        self._tracks_gen = tracks_gen

        self._current_page = -1
        self._pages: list[list[Track]] = []
        self._current_commands: list[int] = []

        self.start(user_message)

    def start(self, user_message: 'agt.Message'):
        self.reload_deadline()
        self._alive = True
        asyncio.create_task(self.service(user_message))

    async def clear(self):
        self._alive = False
        await self._message.delete()

    def reload_deadline(self):
        self._deadline = time.time() + self._lifetime

    def in_lifetime(self):
        return time.time() < self._deadline

    async def service(self, user_message: 'agt.Message', pager_size: int = 10):
        success = await self.prepare_first_page(user_message)
        if not success:
            await user_message.reply(uic.NOT_FOUND)
            await asyncio.sleep(30)
            await self.clear()
            return

        while self._alive and self.in_lifetime():
            if len(self._pages) < pager_size:
                await self.prepare_next_page()

            await asyncio.sleep(1)

        await self.clear()

    def construct_page_keyboard(self):
        # clear commands
        for command_id in self._current_commands:
            self._manager.commander.delete_command(command_id)
        self._current_commands.clear()

        inline_keyboard = []
        page = self._pages[self._current_page]
        # set track buttons
        for track in page:
            duration = time.gmtime(track.duration)
            send_track_command_id = self._manager.commander.create_command(
                self.send_track,
                track,
            )
            self._current_commands.append(send_track_command_id)
            inline_keyboard.append([
                agt.InlineKeyboardButton(
                    text=f"{track.performer} - {track.title} ({duration.tm_min}:{duration.tm_sec:02})",
                    callback_data=str(send_track_command_id),
                )
            ])
        # set page buttons
        page_btns = []
        for i in range(len(self._pages)):
            if i == self._current_page:
                btn_text = f'[{self._current_page + 1}]'
                callback_data = self._manager.commander.DO_NOTHING
            else:
                btn_text = str(i + 1)
                callback_data = self._manager.commander.create_command(
                    self.switch_page, i
                )
                self._current_commands.append(callback_data)

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
        self._pages.append(tracks)

        keyboard = self.construct_page_keyboard()
        self._message = await user_message.reply(
            uic.FINDED, reply_markup=keyboard, disable_web_page_preview=True
        )
        return True

    async def prepare_next_page(self) -> bool:
        tracks = await self.get_tracks_for_page()
        if not tracks:
            return False

        self._pages.append(tracks)

        keyboard = self.construct_page_keyboard()
        await self._message.edit_text(
            uic.FINDED, reply_markup=keyboard, disable_web_page_preview=True
        )
        return True

    async def get_tracks_for_page(self, page_size: int = 10) -> list[Track]:
        return [
            t async for t in aitertools.islice(self._tracks_gen, page_size)
        ]

    # CALLBACKS
    async def send_track(self, callback_query: agt.CallbackQuery, track: Track):
        self.reload_deadline()

        track_data = await track.load_audio()
        await callback_query.message.answer_audio(
            audio=agt.InputFile(
                io.BytesIO(track_data),
                filename=f"{track.performer[:32]}_{track.title[:32]}.mp3"
            ),
            title=track.title,
            performer=track.performer,
            caption=uic.SIGNATURE,
            duration=track.duration,
            parse_mode='html',
        )

    async def switch_page(self, callback_query: agt.CallbackQuery, page_number: int):
        self.reload_deadline()
        self._current_page = page_number

        keyboard = self.construct_page_keyboard()
        await self._message.edit_text(
            uic.FINDED, reply_markup=keyboard, disable_web_page_preview=True
        )
