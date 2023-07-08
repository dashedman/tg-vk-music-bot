import asyncio
from dataclasses import dataclass
from typing import AsyncGenerator

import asynciolimiter
from vk_api import VkApi
from vk_api.audio import VkAudio

from root.models import Track
# from audio import VkAudio
# from async_extend import AsyncVkApi, AsyncVkAudio

from root.sections.base import AbstractSection
from root.utils.m3u8_to_mp3 import m3u8_to_mp3_advanced_direct


@dataclass
class VkTrack(Track):
    vtrack: dict
    audio: VkAudio

    async def load_audio(self, codec: str = 'mp3') -> bytes | None:
        m3u8_url = self.vtrack['url'][:self.vtrack['url'].rfind('?')]
        new_audio = await asyncio.get_running_loop().run_in_executor(
            None,
            m3u8_to_mp3_advanced_direct,
            m3u8_url,
        )
        return new_audio

    def get_id(self) -> str:
        return str(self.vtrack['id']) + '_' + str(self.vtrack['owner_id'])


class VkSection(AbstractSection):
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger

        self.logger.info("Vk autentification...")
        self.session = VkApi(
            login=self.config['login'],
            password=self.config['password'],
            auth_handler=self.auth_handler,
            # token=self.config['access_token'],
        )
        self.session.http.headers['User-agent'] = \
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:94.0)' \
            ' Gecko/20100101 Firefox/94.0'
        self.session.auth()

        self.audio = VkAudio(self.session)
        self.limiter = asynciolimiter.Limiter(40 / 60)  # 40 requests per minute

    def auth_handler(self):
        raise Exception('Auth Handler used!')

    async def get_tracks_gen(self, query: str) -> AsyncGenerator[Track, None]:
        for track in self.audio.search_iter(q=query):
            yield VkTrack(
                track['title'],
                track['artist'],
                track['duration'],
                track,
                self.audio
            )

    async def get_new_songs(self) -> AsyncGenerator[Track, None]:
        for track in self.audio.get_news_iter():
            yield VkTrack(
                track['title'],
                track['artist'],
                track['duration'],
                track,
                self.audio
            )

    async def get_popular_songs(self) -> AsyncGenerator[Track, None]:
        for track in self.audio.get_popular_iter():
            yield VkTrack(
                track['title'],
                track['artist'],
                track['duration'],
                track,
                self.audio
            )
