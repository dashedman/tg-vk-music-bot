from logging import Logger

import ytmusicapi

from tg_vk_music_bot.sections.base import AbstractSection
from tg_vk_music_bot.models import Track


class YoutubeSection(AbstractSection):

    def __init__(self, config, logger: Logger):
        self.config = config
        self.logger = logger

        self.logger.info("Soundcloud initialisation...")
        self.api = ytmusicapi.YTMusic()

    async def get_tracks_gen(self, query):
        json_tracks = self.api.search(query)
        self.logger.debug('Response from Youtube: %s', json_tracks)
        for jt in json_tracks:
            t = Track(
                jt['title'],
                jt['artist']['name'],
                jt['duration_seconds'],
            )
            yield t
