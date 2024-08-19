from dataclasses import dataclass
from typing import AsyncGenerator

import asynciolimiter
import vk_api.exceptions
from vk_api import VkApi
from vk_api.audio import VkAudio

from root.models import Track, Album
# from audio import VkAudio
# from async_extend import AsyncVkApi, AsyncVkAudio

from root.sections.base import AbstractSection
from root.utils.m3u8_to_mp3 import M3u8Loader


@dataclass
class VkTrack(Track):
    section: 'VkSection'
    vtrack: dict
    audio: VkAudio

    async def load_audio(self, codec: str = 'mp3') -> bytes | None:
        if '?' in self.vtrack['url']:
            m3u8_url = self.vtrack['url'][:self.vtrack['url'].rfind('?')]
        else:
            m3u8_url = self.vtrack['url']
        new_audio = await self.section.m3u8_loader.m3u8_to_mp3_wraped(m3u8_url)
        return new_audio

    def get_id(self) -> str:
        return str(self.vtrack['id']) + '_' + str(self.vtrack['owner_id'])


@dataclass
class VkAlbum(Album):
    section: 'VkSection'
    valbum: dict
    audio: VkAudio

    @property
    def plays(self):
        return self.valbum['plays']

    def get_id(self) -> str:
        return str(self.valbum['id']) + '_' + str(self.valbum['owner_id'])

    async def load_tracks(self):
        self.tracks = []
        for raw_track in self.audio.get_iter(
                owner_id=self.valbum['owner_id'],
                album_id=self.valbum['id'],
                access_hash=self.valbum['access_hash']
        ):
            track = VkTrack(
                self.section,
                raw_track['title'],
                raw_track['artist'],
                raw_track['duration'],
                raw_track,
                self.audio
            )
            self.tracks.append(track)


class VkSection(AbstractSection):

    def __init__(self, bot, config, logger):
        self.bot = bot
        self.config = config
        self.logger = logger

        self.logger.info("Vk autentification...")
        self.session = VkApi(
            login=self.config['login'],
            password=self.config['password'],
            auth_handler=self.auth_handler,
            token=self.config['access_token'],
        )
        # self.session.http.headers['User-agent'] = \
        #     'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:94.0)' \
        #     ' Gecko/20100101 Firefox/94.0'
        self.session.http.headers['User-agent'] = \
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0'
        self.session.auth()

        self.audio = VkAudio(self.session)
        self.m3u8_loader = M3u8Loader(self.bot)
        self.limiter = asynciolimiter.Limiter(40 / 60)  # 40 requests per minute

    def auth_handler(self):
        raise Exception('Auth Handler used!')

    def _wrap_track(self, tracks_gen):
        for track in tracks_gen:
            yield VkTrack(
                self,
                track['title'],
                track['artist'],
                track['duration'],
                track,
                self.audio
            )

    def _wrap_album(self, albums_gen):
        for album in albums_gen:
            yield VkAlbum(
                self,
                album['title'],
                album['artist'],
                album['count'],
                None,
                album,
                self.audio
            )

    async def get_tracks_gen(self, query: str) -> AsyncGenerator[Track, None]:
        for t in self._wrap_track(self.audio.search_iter(q=query)):
            yield t

    async def get_new_songs(self) -> AsyncGenerator[Track, None]:
        for t in self._wrap_track(self.audio.get_news_iter()):
            yield t

    async def get_popular_songs(self) -> AsyncGenerator[Track, None]:
        for t in self._wrap_track(self.audio.get_popular_iter()):
            yield t

    async def get_albums_gen(self, query: str) -> AsyncGenerator[Track, None]:
        for a in self._wrap_album(self.audio.search_albums_iter(q=query)):
            yield a

    async def get_tracks_gen_by_id(self, owner_id) -> AsyncGenerator[Track, None]:
        try:
            for t in self._wrap_track(self.audio.get_iter(owner_id=owner_id)):
                yield t
        except vk_api.exceptions.AccessDenied:
            return

    async def get_album_gen_by_id(self, owner_id, album_id) -> AsyncGenerator[Track, None]:
        try:
            for t in self._wrap_track(
                    self.audio.get_iter(owner_id=owner_id, album_id=album_id)
            ):
                yield t
        except vk_api.exceptions.AccessDenied:
            return
