from logging import Logger

import yandex_music

from root.sections.base import AbstractSection
from root.models import Track


class YandexMusicSection(AbstractSection):

    def __init__(self, config, logger: Logger):
        self.config = config
        self.logger = logger

        self.logger.info("YandexMusic initialisation...")
        self.client = yandex_music.ClientAsync()

    async def prepare(self):
        await self.client.init()

    async def get_tracks_gen(self, query):
        search_tracks = await self.client.search(query, type_='track')
        self.logger.debug('Response from YandexMusic: %s', search_tracks)
        ym_tracks: list[yandex_music.Track] = search_tracks.tracks.results
        for yt in ym_tracks:
            t = Track(
                yt.title,
                ', '.join(yt.artists_name()),
                yt.duration_ms // 1000,     # duration in seconds
            )
            yield t
