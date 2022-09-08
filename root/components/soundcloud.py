from soundcloud_lib import SoundcloudAPI
from root.components.base import AbstractComponent


class SoundcloudComponent(AbstractComponent):

    def __init__(self, config, logger):
        self.config = config
        self.logger = logger

        self.logger.info("Soundcloud initialisation...")
        self.api = SoundcloudAPI()

    async def get_tracks_gen(self, query):
        tracks = await self.api.tracks(query)
        for t in tracks.collection:
            yield t
