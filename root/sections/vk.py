from vk_api import VkApi
from vk_api.audio import VkAudio
# from audio import VkAudio
# from async_extend import AsyncVkApi, AsyncVkAudio

from root.sections.base import AbstractSection


class VkSection(AbstractSection):
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger

        self.logger.info("Vk autentification...")
        self.session = VkApi(
            login=self.config['login'],
            password=self.config['password'],
            auth_handler=self.auth_handler
        )
        self.session.http.headers['User-agent'] = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:94.0) Gecko/20100101 Firefox/94.0'
        self.session.auth(token_only=True)

        self.audio = VkAudio(self.session)

    def auth_handler(self):
        raise Exception('Auth Handler used!')
