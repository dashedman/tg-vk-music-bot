from sclib.asyncio import SoundcloudAPI
from root.sections.base import AbstractSection


class SoundcloudSection(AbstractSection):

    def __init__(self, config, logger):
        self.config = config
        self.logger = logger

        self.logger.info("Soundcloud initialisation...")
        self.api = SoundcloudAPI()

    async def get_tracks_gen(self, query):
        raw_tracks = await self.api.
        for t in tracks.collection:
            yield t
