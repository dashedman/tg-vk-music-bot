from dataclasses import dataclass

import tg_vk_music_bot.sections.base


@dataclass
class Track:
    section: 'tg_vk_music_bot.sections.base.AbstractSection'
    title: str
    performer: str
    duration: int

    @property
    def full_name(self):
        return f'{self.performer} - {self.title}'

    async def load_audio(self) -> bytes | None:
        raise NotImplementedError()

    def get_id(self) -> str:
        raise NotImplementedError()


@dataclass
class Album:
    section: 'tg_vk_music_bot.sections.base.AbstractSection'
    title: str
    performer: str
    size: int
    tracks: list[Track] | None

    @property
    def full_name(self):
        return f'{self.performer} - {self.title}'

    @property
    def plays(self):
        raise NotImplementedError()

    async def load_tracks(self):
        raise NotImplementedError()

    def get_id(self) -> str:
        raise NotImplementedError()
