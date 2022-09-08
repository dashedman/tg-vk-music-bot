import asyncio

import aiohttp
import orjson

from .schemas import Tracks


class SoundcloudAPI:
    api_url = 'https://api.soundcloud.com/'

    def __init__(self):
        pass

    async def _request_to_api(self, rest_method: str, params: dict[str, str]):
        method_url = self.api_url + rest_method
        async with aiohttp.ClientSession() as session:
            resp = await session.get(method_url, params=params)
            return await resp.json(loads=orjson.loads)

    async def tracks(self, q: str):
        tracks_json = await self._request_to_api('tracks', {
            'q': q
        })
        return Tracks.from_json(tracks_json)



