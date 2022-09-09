import asyncio
import logging

import aiohttp
import orjson

from .schemas import Tracks


class SoundcloudAPI:
    api_url = 'https://api.soundcloud.com/'

    def __init__(self):
        self.logger = logging.getLogger('SoundcloudAPI')

    async def _request_to_api(self, rest_method: str, params: dict[str, str]):
        method_url = self.api_url + rest_method
        async with aiohttp.ClientSession() as session:
            self.logger.debug('Request to "%s", params=%s', method_url, params)
            resp = await session.get(method_url, params=params)
            json = await resp.json(loads=orjson.loads)
            self.logger.debug('Response - %25s', json)
            return json

    async def tracks(self, q: str):
        tracks_json = await self._request_to_api('tracks', {
            'q': q
        })
        return Tracks.from_json(tracks_json)



