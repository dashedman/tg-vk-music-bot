import asyncio
from dataclasses import dataclass, field
from typing import Callable, Coroutine, NewType

import aiogram.types as agt

from tg_vk_music_bot import ui_constants as uic

CommandId = NewType('CommandId', int)


@dataclass
class CommandUnit:
    id: CommandId
    on_execute: Callable[..., Coroutine]
    args: field(default={})
    kwargs: field(default=[])


class CallbackCommander:
    DO_NOTHING = CommandId(-1)

    def __init__(self):
        self._last_id = 0
        self._ids_registry: dict[CommandId, CommandUnit] = {}

    def _get_next_id(self) -> CommandId:
        while self._last_id in self._ids_registry:
            self._last_id = (self._last_id + 1) % 1000000
        return self._last_id

    async def execute(self, callback_query: agt.CallbackQuery):
        command_id = CommandId(int(callback_query.data))
        if command_id == self.DO_NOTHING:
            return

        unit = self._ids_registry.get(command_id)
        if unit is None:
            # delete callback message
            await callback_query.message.edit_text(uic.OLD_MESSAGE)
            await asyncio.sleep(30)
            await callback_query.message.delete()
            return

        await unit.on_execute(callback_query, *unit.args, **unit.kwargs)

    def create_command(self, command_callback, *args, **kwargs) -> CommandId:
        command_id = self._get_next_id()
        self._ids_registry[command_id] = CommandUnit(
            command_id,
            command_callback,
            args, kwargs,
        )
        return command_id

    def delete_command(self, cid: CommandId):
        del self._ids_registry[cid]
