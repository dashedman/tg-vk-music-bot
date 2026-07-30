from dataclasses import dataclass
from logging import Logger

import yandex_music

from tg_vk_music_bot.sections.base import AbstractSection
from tg_vk_music_bot.models import Track


class LoginResponse:
    """"
    status: ok
       uid: 1234567890
       display_name: John
       public_name: John
       firstname: John
       lastname: McClane
       gender: m
       display_login: j0hn.mcclane
       normalized_display_login: j0hn-mcclane
       native_default_email: j0hn.mcclane@yandex.ru
       avatar_url: XXX
       is_avatar_empty: True
       public_id: XXX
       access_token: XXX
       cloud_token: XXX
       x_token: XXX
       x_token_issued_at: 1607490000
       access_token_expires_in: 24650000
       x_token_expires_in: 24650000
    status: error
       errors: [captcha.required]
       captcha_image_url: XXX
    status: error
       errors: [account.not_found]
       errors: [password.not_matched]
    """

    def __init__(self, resp: dict):
        self.raw = resp

    @property
    def ok(self):
        return self.raw.get("status") == "ok"

    @property
    def errors(self):
        return self.raw.get("errors", [])

    @property
    def error(self):
        return self.raw['errors'][0]

    @property
    def display_login(self):
        return self.raw['display_login']

    @property
    def x_token(self):
        return self.raw['x_token']

    @property
    def magic_link_email(self):
        return self.raw.get("magic_link_email")

    @property
    def error_captcha_required(self):
        return "captcha.required" in self.errors


@dataclass
class YandexTrack(Track):
    ytrack: yandex_music.Track

    async def load_audio(self, codec: str = 'mp3') -> bytes | None:
        data = None

        if self.ytrack.download_info is None:
            await self.ytrack.get_download_info_async()

        download_info_max_bitrate = sorted(
            self.ytrack.download_info,
            key=lambda d_info: d_info.bitrate_in_kbps,
            reverse=True
        )

        for info in download_info_max_bitrate:
            if info.codec == codec:
                # load from info
                if info.direct_link is None:
                    await info.get_direct_link_async()

                data = await info.client.request.retrieve(info.direct_link)
                # end load
                break
        return data


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
            t = YandexTrack(
                yt.title,
                ', '.join(yt.artists_name()),
                yt.duration_ms // 1000,     # duration in seconds
                yt,
            )
            yield t

    async def login_password(self, password: str) -> LoginResponse:
        """Login using password or key-app (30 second password)."""
        assert self.auth_payload
        # step 3: password or 30 seconds key
        r = await self.session.post(
            "https://passport.yandex.ru/registration-validations/auth/multi_step/commit_password",
            data={
                **self.auth_payload,
                "password": password,
                "retpath": "https://passport.yandex.ru/am/finish?status=ok&from=Login"
            },
            proxy=self.proxy
        )
        resp = await r.json()
        if resp["status"] != "ok":
            return LoginResponse(resp)

        if "redirect_url" in resp:
            return LoginResponse({"errors": ["redirect.unsupported"]})

        # step 4: x_token
        return await self.login_cookies()
