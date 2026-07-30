import json
import logging
import random
import re
import threading
import time
import datetime

from urllib.parse import urlparse, parse_qs, unquote
from pprint import pprint, pformat

from bs4 import BeautifulSoup

import asyncio
import requests
import requests_async as arequests
import six

from requests_async import adapters
from requests_async.cookies import extract_cookies_to_jar

from h2.exceptions import ProtocolError


import jconfig
from vk_api.enums import VkUserPermissions
from vk_api.exceptions import *
from vk_api.utils import (
    code_from_number, search_re, clear_string,
    cookies_to_list, set_cookies_from_list
)
from vk_api.audio_url_decoder import decode_audio_url



RE_LOGIN_HASH = re.compile(r'name="lg_h" value="([a-z0-9]+)"')
RE_CAPTCHAID = re.compile(r"onLoginCaptcha\('(\d+)'")
RE_NUMBER_HASH = re.compile(r"al_page: '3', hash: '([a-z0-9]+)'")
RE_AUTH_HASH = re.compile(
    r"\{.*?act: 'a_authcheck_code'.+?hash: '([a-z_0-9]+)'.*?\}"
)
RE_TOKEN_URL = re.compile(r'location\.href = "(.*?)"\+addr;')

RE_PHONE_PREFIX = re.compile(r'label ta_r">\+(.*?)<')
RE_PHONE_POSTFIX = re.compile(r'phone_postfix">.*?(\d+).*?<')


DEFAULT_USER_SCOPE = sum(VkUserPermissions)

"""Библиотека которая реализует requests
 имеет баг с состоянием гонки
 поэтому вписан костыль синхронизации"""

class SyncSession(arequests.Session):

    sync_flag = False
    async def send(self, request, **kwargs):
        """Send a given PreparedRequest.

        :rtype: requests.Response
        """
        # Set defaults that the hooks can utilize to ensure they always have
        # the correct parameters to reproduce the previous request.
        kwargs.setdefault("stream", self.stream)
        kwargs.setdefault("verify", self.verify)
        kwargs.setdefault("cert", self.cert)
        kwargs.setdefault("proxies", self.proxies)

        # It's possible that users might accidentally send a Request object.
        # Guard against that specific failure case.
        if isinstance(request, requests.models.Request):
            raise ValueError("You can only send PreparedRequests.")

        # Set up variables needed for resolve_redirects and dispatching of hooks
        allow_redirects = kwargs.pop("allow_redirects", True)
        stream = kwargs.get("stream")
        hooks = request.hooks

        # Get the appropriate adapter to use
        adapter = self.get_adapter(url=request.url)

        # Start time (approximately) of the request
        start = requests.sessions.preferred_clock()

        while self.sync_flag:
            await asyncio.sleep(0)
        # Send the request
        self.sync_flag = True
        r = await adapter.send(request, **kwargs)
        self.sync_flag = False

        # Total elapsed time of the request (approximately)
        elapsed = requests.sessions.preferred_clock() - start
        r.elapsed = datetime.timedelta(seconds=elapsed)

        # Response manipulation hooks
        r = requests.hooks.dispatch_hook("response", hooks, r, **kwargs)

        # Persist cookies
        if r.history:

            # If the hooks create history then we want those cookies too
            for resp in r.history:
                extract_cookies_to_jar(self.cookies, resp.request, resp.raw)

        extract_cookies_to_jar(self.cookies, request, r.raw)

        # Redirect resolving.
        history = []
        if allow_redirects:
            async for resp in self.resolve_redirects(r, request, **kwargs):
                history.append(resp)

        # Shuffle things around if there's history.
        if history:
            # Insert the first (original) request at the start
            history.insert(0, r)
            # Get the last request made
            r = history.pop()
            r.history = history

        # If redirects aren't being followed, store the response on the Request for Response.next().
        if not allow_redirects:
            try:
                redirect_gen = self.resolve_redirects(
                    r, request, yield_requests=True, **kwargs
                )
                r._next = await redirect_gen.__anext__()
            except StopAsyncIteration:
                pass

        if not stream:
            await r.read()

        return r

class AsyncVkApi(object):
    """
    VkApi() from vk_api
    """

    RPS_DELAY = 0.34  # ~3 requests per second

    def __init__(self, login=None, password=None, token=None,
                 auth_handler=None, captcha_handler=None,
                 config=jconfig.Config, config_filename='vk_config.v2.json',
                 api_version='5.92', app_id=6222115, scope=DEFAULT_USER_SCOPE,
                 client_secret=None, session=None, loop = None):

        self.login = login
        self.password = password

        self.token = {'access_token': token}

        self.api_version = api_version
        self.app_id = app_id
        self.scope = scope
        self.client_secret = client_secret

        self.storage = config(self.login, filename=config_filename)


        self.http = session or SyncSession()#requests.Session()
        self.loop = loop or asyncio.get_event_loop()

        if not session:
            self.http.headers.update({
                'User-agent': 'Mozilla/5.0 (Windows NT 6.1; rv:52.0) '
                              'Gecko/20100101 Firefox/52.0'
            })

        self.last_request = 0.0

        self.error_handlers = {
            NEED_VALIDATION_CODE: self.need_validation_handler,
            CAPTCHA_ERROR_CODE: captcha_handler or self.captcha_handler,
            TOO_MANY_RPS_CODE: self.too_many_rps_handler,
            TWOFACTOR_CODE: auth_handler or self.auth_handler
        }

        self.lock = threading.Lock()

        self.logger = logging.getLogger('vk_api')

    @property
    def _sid(self):
        return (
            self.http.cookies.get('remixsid') or
            self.http.cookies.get('remixsid6')
        )

    def sync_auth(self, reauth=False, token_only=False):
        self.loop.run_until_complete(self.auth(reauth, token_only))

    async def auth(self, reauth=False, token_only=False):
        """ Аутентификация

        :param reauth: Позволяет переавторизоваться, игнорируя сохраненные
            куки и токен

        :param token_only: Включает оптимальную стратегию аутентификации, если
            необходим только access_token

            Например если сохраненные куки не валидны,
            но токен валиден, то аутентификация пройдет успешно

            При token_only=False, сначала проверяется
            валидность куки. Если кука не будет валидна, то
            будет произведена попытка аутетификации с паролем.
            Тогда если пароль не верен или пароль не передан,
            то аутентификация закончится с ошибкой.

            Если вы не делаете запросы к веб версии сайта
            используя куки, то лучше использовать
            token_only=True
        """

        if not self.login:
            raise LoginRequired('Login is required to auth')

        self.logger.info('Auth with login: {}'.format(self.login))

        set_cookies_from_list(
            self.http.cookies,
            self.storage.setdefault('cookies', [])
        )

        self.token = self.storage.setdefault(
            'token', {}
        ).setdefault(
            'app' + str(self.app_id), {}
        ).get('scope_' + str(self.scope))

        if token_only:
            await self._auth_token(reauth=reauth)
        else:
            await self._auth_cookies(reauth=reauth)

    async def _auth_cookies(self, reauth=False):

        if reauth:
            self.logger.info('Auth forced')

            self.storage.clear_section()

            await self._vk_login()
            await self._api_login()
            return

        if not await self.check_sid():
            self.logger.info(
                'remixsid from config is not valid: {}'.format(
                    self._sid
                )
            )

            await self._vk_login()
        else:
            await self._pass_security_check()

        if not (await self._check_token()):
            self.logger.info(
                'access_token from config is not valid: {}'.format(
                    self.token
                )
            )

            await self._api_login()
        else:
            self.logger.info(f'access_token from config is valid')

    async def _auth_token(self, reauth=False):

        if not reauth and (await self._check_token()):
            self.logger.info('access_token from config is valid')
            return

        if reauth:
            self.logger.info('Auth (API) forced')

        if (await self.check_sid()):
            await self._pass_security_check()
            await self._api_login()

        elif self.password:
            self._vk_login()
            self._api_login()

    async def _vk_login(self, captcha_sid=None, captcha_key=None):
        """ Авторизация ВКонтакте с получением cookies remixsid

        :param captcha_sid: id капчи
        :type captcha_key: int or str

        :param captcha_key: ответ капчи
        :type captcha_key: str
        """

        self.logger.info('Logging in...')

        if not self.password:
            raise PasswordRequired('Password is required to login')

        self.http.cookies.clear()

        # Get cookies
        response = await self.http.get('https://vk.com/')

        values = {
            'act': 'login',
            'role': 'al_frame',
            '_origin': 'https://vk.com',
            'utf8': '1',
            'email': self.login,
            'pass': self.password,
            'lg_h': search_re(RE_LOGIN_HASH, response.text)
        }

        if captcha_sid and captcha_key:
            self.logger.info(
                'Using captcha code: {}: {}'.format(
                    captcha_sid,
                    captcha_key
                )
            )

            values.update({
                'captcha_sid': captcha_sid,
                'captcha_key': captcha_key
            })

        response = await self.http.post('https://login.vk.com/', values)

        if 'onLoginCaptcha(' in response.text:
            self.logger.info('Captcha code is required')

            captcha_sid = search_re(RE_CAPTCHAID, response.text)
            captcha = Captcha(self, captcha_sid, self._vk_login)

            return self.error_handlers[CAPTCHA_ERROR_CODE](captcha)

        if 'onLoginReCaptcha(' in response.text:
            self.logger.info('Captcha code is required (recaptcha)')

            captcha_sid = str(random.random())[2:16]
            captcha = Captcha(self, captcha_sid, self._vk_login)

            return self.error_handlers[CAPTCHA_ERROR_CODE](captcha)

        if 'onLoginFailed(4' in response.text:
            raise BadPassword('Bad password')

        if 'act=authcheck' in response.text:
            self.logger.info('Two factor is required')

            response = await self.http.get('https://vk.com/login?act=authcheck')

            self._pass_twofactor(response)

        if self._sid:
            self.logger.info('Got remixsid')

            self.storage.cookies = cookies_to_list(self.http.cookies)
            self.storage.save()
        else:
            raise AuthError(
                'Unknown error. Please send bugreport to vk_api@python273.pw'
            )

        response = await self._pass_security_check(response)

        if 'act=blocked' in response.url:
            raise AccountBlocked('Account is blocked')

    async def _pass_twofactor(self, auth_response):
        """ Двухфакторная аутентификация

        :param auth_response: страница с приглашением к аутентификации
        """
        code, remember_device = self.error_handlers[TWOFACTOR_CODE]()

        auth_hash = search_re(RE_AUTH_HASH, auth_response.text)

        values = {
            'act': 'a_authcheck_code',
            'al': '1',
            'code': code,
            'remember': int(remember_device),
            'hash': auth_hash,
        }

        response = await self.http.post('https://vk.com/al_login.php', values)
        data = json.loads(response.text.lstrip('<!--'))
        status = data['payload'][0]

        if status == '4':  # OK
            path = json.loads(data['payload'][1][0])
            return await self.http.get('https://vk.com' + path)

        elif status in [0, '8']:  # Incorrect code
            return self._pass_twofactor(auth_response)

        elif status == '2':
            raise TwoFactorError('Recaptcha required')

        raise TwoFactorError('Two factor authentication failed')

    async def _pass_security_check(self, response=None):
        """ Функция для обхода проверки безопасности (запрос номера телефона)

        :param response: ответ предыдущего запроса, если есть
        """

        self.logger.info('Checking security check request')

        if response is None:
            response = await self.http.get('https://vk.com/settings')

        if 'security_check' not in response.url:
            self.logger.info('Security check is not required')
            return response

        phone_prefix = clear_string(search_re(RE_PHONE_PREFIX, response.text))
        phone_postfix = clear_string(
            search_re(RE_PHONE_POSTFIX, response.text))

        code = None
        if self.login and phone_prefix and phone_postfix:
            code = code_from_number(phone_prefix, phone_postfix, self.login)

        if code:
            number_hash = search_re(RE_NUMBER_HASH, response.text)

            values = {
                'act': 'security_check',
                'al': '1',
                'al_page': '3',
                'code': code,
                'hash': number_hash,
                'to': ''
            }

            response = await self.http.post('https://vk.com/login.php', values)

            if response.text.split('<!>')[4] == '4':
                return response

        if phone_prefix and phone_postfix:
            raise SecurityCheck(phone_prefix, phone_postfix)

        raise SecurityCheck(response=response)

    async def check_sid(self):
        """ Проверка Cookies remixsid на валидность """

        self.logger.info('Checking remixsid...')

        if not self._sid:
            self.logger.info('No remixsid')
            return

        response = (await self.http.get('https://vk.com/feed2.php')).json()

        if response['user']['id'] != -1:
            self.logger.info('remixsid is valid')
            return response

        self.logger.info('remixsid is not valid')

    async def _api_login(self):
        """ Получение токена через Desktop приложение """

        if not self._sid:
            raise AuthError('API auth error (no remixsid)')

        for cookie_name in ['p', 'l']:
            if not self.http.cookies.get(cookie_name, domain='.login.vk.com'):
                raise AuthError('API auth error (no login cookies)')

        response = await self.http.get(
            'https://oauth.vk.com/authorize',
            params={
                'client_id': self.app_id,
                'scope': self.scope,
                'response_type': 'token'
            }
        )

        if 'act=blocked' in response.url:
            raise AccountBlocked('Account is blocked')

        if 'access_token' not in response.url:
            url = search_re(RE_TOKEN_URL, response.text)

            if url:
                response = await self.http.get(url)

        if 'access_token' in response.url:
            parsed_url = urlparse(response.url)
            parsed_query = parse_qs(parsed_url.query)

            if 'authorize_url' in parsed_query:
                parsed_url = urlparse(unquote(parsed_query['authorize_url'][0]))

            parsed_query = parse_qs(parsed_url.fragment)

            token = {k: v[0] for k, v in parsed_query.items()}

            if not isinstance(token.get('access_token'), str):
                raise AuthError(get_unknown_exc_str('API AUTH; no access_token'))
            #params = response.url.split('#', 1)[1].split('&')
            #token = dict(param.split('=', 1) for param in params)

            self.token = token

            self.storage.setdefault(
                'token', {}
            ).setdefault(
                'app' + str(self.app_id), {}
            )['scope_' + str(self.scope)] = token

            self.storage.save()

            self.logger.info('Got access_token')

        elif 'oauth.vk.com/error' in response.url:
            error_data = response.json()

            error_text = error_data.get('error_description')

            # Deletes confusing error text
            if error_text and '@vk.com' in error_text:
                error_text = error_data.get('error')

            raise AuthError('API auth error: {}'.format(error_text))

        else:
            raise AuthError('Unknown API auth error')

    async def server_auth(self):
        """ Серверная авторизация """
        values = {
            'client_id': self.app_id,
            'client_secret': self.client_secret,
            'v': self.api_version,
            'grant_type': 'client_credentials'
        }

        response = (await self.http.post(
            'https://oauth.vk.com/access_token', values
        )).json()

        if 'error' in response:
            raise AuthError(response['error_description'])
        else:
            self.token = response

    async def code_auth(self, code, redirect_url):
        """ Получение access_token из code """
        values = {
            'client_id': self.app_id,
            'client_secret': self.client_secret,
            'v': self.api_version,
            'redirect_uri': redirect_url,
            'code': code,
        }

        response = (await self.http.post(
            'https://oauth.vk.com/access_token', values
        )).json()

        if 'error' in response:
            raise AuthError(response['error_description'])
        else:
            self.token = response
        return response

    async def _check_token(self):
        """ Проверка access_token юзера на валидность """

        if self.token:
            try:
                await self.method('stats.trackVisitor')
            except ApiError:
                return False

            return True

    def captcha_handler(self, captcha):
        """ Обработчик капчи (http://vk.com/dev/captcha_error)

        :param captcha: объект исключения `Captcha`
        """

        raise captcha

    def need_validation_handler(self, error):
        """ Обработчик проверки безопасности при запросе API
            (http://vk.com/dev/need_validation)

        :param error: исключение
        """

        pass  # TODO: write me

    def http_handler(self, error):
        """ Обработчик ошибок соединения

        :param error: исключение
        """

        pass

    def too_many_rps_handler(self, error):
        """ Обработчик ошибки "Слишком много запросов в секунду".
            Ждет полсекунды и пробует отправить запрос заново

        :param error: исключение
        """

        self.logger.warning('Too many requests! Sleeping 0.5 sec...')

        time.sleep(0.5)
        return error.try_method()

    def auth_handler(self):
        """ Обработчик двухфакторной аутентификации """

        raise AuthError('No handler for two-factor authentication')

    def get_api(self):
        """ Возвращает VkApiMethod(self)

            Позволяет обращаться к методам API как к обычным классам.
            Например vk.wall.get(...)
        """

        return VkApiMethod(self)

    async def method(self, method, values=None, captcha_sid=None, captcha_key=None,
               raw=False):
        """ Вызов метода API

        :param method: название метода
        :type method: str

        :param values: параметры
        :type values: dict

        :param captcha_sid: id капчи
        :type captcha_key: int or str

        :param captcha_key: ответ капчи
        :type captcha_key: str

        :param raw: при False возвращает `response['response']`
                    при True возвращает `response`
                    (может понадобиться для метода execute для получения
                    execute_errors)
        :type raw: bool
        """

        values = values.copy() if values else {}

        if 'v' not in values:
            values['v'] = self.api_version

        if self.token:
            values['access_token'] = self.token['access_token']

        if captcha_sid and captcha_key:
            values['captcha_sid'] = captcha_sid
            values['captcha_key'] = captcha_key

        with self.lock:
            # Ограничение 3 запроса в секунду
            delay = self.RPS_DELAY - (time.time() - self.last_request)

            if delay > 0:
                time.sleep(delay)

            response = await self.http.post(
                'https://api.vk.com/method/' + method,
                values
            )
            self.last_request = time.time()

        if response.ok:
            response = response.json()
        else:
            error = ApiHttpError(self, method, values, raw, response)
            response = self.http_handler(error)

            if response is not None:
                return response

            raise error

        if 'error' in response:
            error = ApiError(self, method, values, raw, response['error'])

            if error.code in self.error_handlers:
                if error.code == CAPTCHA_ERROR_CODE:
                    error = Captcha(
                        self,
                        error.error['captcha_sid'],
                        self.method,
                        (method,),
                        {'values': values, 'raw': raw},
                        error.error['captcha_img']
                    )

                response = self.error_handlers[error.code](error)

                if response is not None:
                    return response

            raise error

        return response if raw else response['response']


RE_ALBUM_ID = re.compile(r'act=audio_playlist(-?\d+)_(\d+)')
RE_ACCESS_HASH = re.compile(r'access_hash=(\w+)')
RE_M3U8_TO_MP3 = re.compile(r'/[0-9a-f]+(/audios)?/([0-9a-f]+)/index.m3u8')

TRACKS_PER_USER_PAGE = 2000
TRACKS_PER_ALBUM_PAGE = 2000
ALBUMS_PER_USER_PAGE = 100

RPS_DELAY = {
    'reload_audio': 2, # ~ 20 req in 10 sec
    'load_section': 1.5, # ~ 40 req in 60 sec
    'load_catalog_section': 1.5, # ~ 40 req in 60 sec
    'section': 0,
    'ad_event': 0,      # don't know
    'search_stats': 0,  # don't know
    'listened_data': 0, # don't know
    'audio_status': 0,  # don't know
}

DEFAULT_COOKIES = [
    {  # если не установлено, то первый запрос ломается
        'version': 0,
        'name': 'remixaudio_show_alert_today',
        'value': '0',
        'port': None,
        'port_specified': False,
        'domain': '.vk.com',
        'domain_specified': True,
        'domain_initial_dot': True,
        'path': '/',
        'path_specified': True,
        'secure': True,
        'expires': None,
        'discard': False,
        'comment': None,
        'comment_url': None,
        'rfc2109': False,
        'rest': {}
    }, {  # для аудио из постов
        'version': 0,
        'name': 'remixmdevice',
        'value': '1920/1080/2/!!-!!!!',
        'port': None,
        'port_specified': False,
        'domain': '.vk.com',
        'domain_specified': True,
        'domain_initial_dot': True,
        'path': '/',
        'path_specified': True,
        'secure': True,
        'expires': None,
        'discard': False,
        'comment': None,
        'comment_url': None,
        'rfc2109': False,
        'rest': {}
    }
]

AUDIO_ITEM = [
    "ID",          #0
    "OWNER_ID",    #1
    "URL",         #2
    "TITLE",       #3
    "PERFORMER",   #4
    "DURATION",    #5
    "ALBUM_ID",    #6
    "7",           #7
    "AUTHOR_LINK", #8
    "LYRICS",      #9
    "FLAGS",       #10
    "CONTEXT",     #11
    "EXTRA",       #12
    "HASHES",      #13
    "COVER_URL",   #14
    "ADS",         #15
    "SUBTITLE",    #16
    "MAIN_ARTISTS",#17
    "FEAT_ARTISTS",#18
    "ALBUM",       #19
    "TRACK_CODE"   #20
]
AUDIO_ITEM_INDEX = {key:index for index, key in enumerate(AUDIO_ITEM)}

class MyActLock():
    def __init__(self, rps_delay):
        self._rps_delay = rps_delay
        self._last_request = 0.0
        self._is_locked =  False
        self._counter = 0

    async def __aenter__(self):
        self._counter += 1
        while self._is_locked or self._rps_delay > (time.time() - self._last_request):
            delay = self._rps_delay - (time.time() - self._last_request)
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                await asyncio.sleep(0)
        self._is_locked = True
        self._last_request = time.time()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._is_locked = False
        self._counter -= 1

    async def wait(self):
        while self._is_locked and self._counter != 0:
            await asyncio.sleep(0)

class AsyncVkAudio(object):
    """
    VkAudio from vk_api.audio
    """

    __slots__ = ('_vk', 'user_id', 'convert_m3u8_links', 'lock')

    def __init__(self, vk, convert_m3u8_links=True):
        self._vk = vk
        self.user_id = self._vk.loop.run_until_complete(vk.method('users.get'))[0]['id']
        self.convert_m3u8_links = convert_m3u8_links

        #for rps delays
        self.lock = {act: MyActLock(RPS_DELAY[act]) for act in RPS_DELAY}

        set_cookies_from_list(self._vk.http.cookies, DEFAULT_COOKIES)

        self._vk.loop.run_until_complete(self._vk.http.get('https://m.vk.com/'))  # load cookies

    def _scrap_id(self, audios):
        """ Парсинг id хэшей аудиозаписи из json объекта """
        ids = []
        for audio in audios:
            _, _, actionHash, _, _, URLHash, _ = audio[AUDIO_ITEM_INDEX["HASHES"]].split("/")

            full_id = (
                str(audio[AUDIO_ITEM_INDEX["OWNER_ID"]]),
                str(audio[AUDIO_ITEM_INDEX["ID"]]),
                actionHash,
                URLHash
            )
            if all(full_id):
                ids.append(full_id)
        return ids

    def _filter_by_id(self, audios):
        """ Парсинг id хэшей аудиозаписи из json объекта """
        lst = []
        for audio in audios:
            _, _, actionHash, _, _, URLHash, _ = audio[AUDIO_ITEM_INDEX["HASHES"]].split("/")

            if actionHash and URLHash:
                lst.append(audio)
        return lst

    def _scrap_json(self, html_page):
        """ Парсинг списка хэшей ауфдиозаписей новинок или популярных + nextFrom&sesionId """

        find_json_pattern = r"new AudioPage\(.*?(\{.*\})"
        match = re.search(find_json_pattern, html_page).group(1)
        return match

    def _wrap_audio(self, raw_audio):
        try:
            return {AUDIO_ITEM[index]: raw_audio[index] for index in range(len(AUDIO_ITEM))}
        except:
            self._vk.logger.error(pformat(f"\n\nWRAP:\n\n{raw_audio}"))
            raise

    async def wait(self):
        for lock in self.lock.values():
            await lock.wait()

    async def _al_audio(self, act, **datas):
        """
        acts:
            - section
            - load_catalog_section
            - load_section
            - ad_event
            - search_stats
            - reload_audio
            - listened_data
            - audio_status

        payload error codes:
            0 - ok
            3 - ??? (reauth to fix)
            8 - too much requests
        """

        #delay lock

        try:
            async with self.lock[act]:
                response = await self._vk.http.post(
                    'https://vk.com/al_audio.php',
                    data={'al': 1, 'act': act, **datas}
                )
        except ProtocolError:
            await self._vk.auth(reauth=True)
            self._vk.logger.warning(f"ProtocolError. ReAuth")
        else:
            json_response = json.loads(response.text.replace('<!--', ''))

            if int(json_response['payload'][0]) == 0:
                return json_response

            self._vk.logger.warning(f"Error code: {json_response['payload'][0]}")

            if not json_response['payload'][1]:
                raise AccessDenied(
                    f"You don\'t have permissions to browse\'s audio.\n Error code: {json_response['payload'][0]}. Act: {act}\n DATA:\n{pformat(datas)}\nREAL DATA:{pformat({'al': 1, 'act': act, **datas})}\n JSON RESPONSE:\n{pformat(json_response)}\n"
                )

            if int(json_response['payload'][0]) == 3:
                await self._vk.auth(reauth=True)

        async with self.lock[act]:
            response = await self._vk.http.post(
                'https://vk.com/al_audio.php',
                data={'al': 1, 'act': act, **datas}
            )
        json_response = json.loads(response.text.replace('<!--', ''))

        if int(json_response['payload'][0]) != 0:
            sid_valid = await self._vk.check_sid()
            self._vk.logger.error(f"Remixsid is valid: {sid_valid}")
            self._vk.logger.error(f"DATA:\n{pformat(datas)}")
            self._vk.logger.error(f"PAYLOAD:\n{pformat(json_response['payload'])}")
            raise Exception(f"Al_Audio Error code: {json_response['payload'][0]}")

        return json_response

    async def get_iter(self, owner_id=None, album_id=None, access_hash=None):
        """ Получить список аудиозаписей пользователя (по частям)
        :param owner_id: ID владельца (отрицательные значения для групп)
        :param album_id: ID альбома
        :param access_hash: ACCESS_HASH альбома
        """

        if owner_id is None:
            owner_id = self.user_id

        if album_id is not None:
            offset_diff = TRACKS_PER_ALBUM_PAGE
        else:
            offset_diff = TRACKS_PER_USER_PAGE

        offset = 0
        while True:
            response = (await self._vk.http.post(
                'https://m.vk.com/audio',
                data={
                    'act': 'load_section',
                    'owner_id': owner_id,
                    'playlist_id': album_id if album_id else -1,
                    'offset': offset,
                    'type': 'playlist',
                    'access_hash': access_hash,
                    'is_loading_all': 1
                },
                allow_redirects=False
            )).json()

            if not response['data'][0]:
                raise AccessDenied(
                    'You don\'t have permissions to browse {}\'s albums'.format(
                        owner_id
                    )
                )

            ids = scrap_ids(
                response['data'][0]['list']
            )
            if not ids:
                break

            tracks = scrap_tracks(
                ids,
                self.user_id,
                self._vk.http,
                convert_m3u8_links=self.convert_m3u8_links
            )

            async for i in tracks:
                yield i

            if response['data'][0]['hasMore']:
                offset += offset_diff
            else:
                break

    async def get(self, owner_id=None, album_id=None, access_hash=None):
        """ Получить список аудиозаписей пользователя
        :param owner_id: ID владельца (отрицательные значения для групп)
        :param album_id: ID альбома
        :param access_hash: ACCESS_HASH альбома
        """

        return list(await self.get_iter(owner_id, album_id, access_hash))

    async def get_albums_iter(self, owner_id=None):
        """ Получить список альбомов пользователя (по частям)
        :param owner_id: ID владельца (отрицательные значения для групп)
        """

        if owner_id is None:
            owner_id = self.user_id

        offset = 0

        while True:
            response = await self._vk.http.get(
                'https://m.vk.com/audio?act=audio_playlists{}'.format(
                    owner_id
                ),
                params={
                    'offset': offset
                },
                allow_redirects=False
            )

            if not response.text:
                raise AccessDenied(
                    'You don\'t have permissions to browse {}\'s albums'.format(
                        owner_id
                    )
                )

            albums = scrap_albums(response.text)

            if not albums:
                break

            async for i in albums:
                yield i

            offset += ALBUMS_PER_USER_PAGE

    async def get_albums(self, owner_id=None):
        """ Получить список альбомов пользователя
        :param owner_id: ID владельца (отрицательные значения для групп)
        """

        return list(await self.get_albums_iter(owner_id))

    async def search_user(self, owner_id=None, q=''):
        """ Искать по аудиозаписям пользователя
        :param owner_id: ID владельца (отрицательные значения для групп)
        :param q: запрос
        """

        if owner_id is None:
            owner_id = self.user_id

        json_response = await self._al_audio(
            'section',
            owner_id=owner_id,
            section='search',
            q=q
        )

        if json_response['payload'][1][1]['playlists']:

            ids = scrap_ids(
                json_response['payload'][1][1]['playlists'][0]['list']
            )

            tracks = scrap_tracks(
                ids,
                self.user_id,
                self._vk.http,
                convert_m3u8_links=self.convert_m3u8_links
            )

            return list(tracks)
        else:
            return []

    async def search(self, q, count=100, offset=0):
        """ Искать аудиозаписи
        :param q: запрос
        :param count: количество
        """

        audio_list = []
        agen = self.search_iter(q, offset=offset)
        for i in range(count):
            try:
                audio_list.append(await agen.__anext__())
            except StopAsyncIteration:
                pass
        return audio_list

    async def search_iter(self, q, offset=0):
        """ Искать аудиозаписи (генератор)
        :param q: запрос
        """
        offset_left = 0

        json_response = await self._al_audio(
            'section',
            owner_id=self.user_id,
            section='search',
            q=q
        )

        try:
            while json_response['payload'][1][1]['playlist']:
                #pprint(json_response['payload'][1][1]['playlist']['list'])

                list = json_response['payload'][1][1]['playlist']['list']

                clear_list = self._filter_by_id(list)
                if not clear_list:
                    break

                if offset_left + len(clear_list) >= offset:
                    if offset_left < offset:
                        clear_list = clear_list[offset - offset_left:]

                    for raw_audio in clear_list:
                        yield self._wrap_audio(raw_audio)

                offset_left += len(clear_list)

                json_response = await self._al_audio(
                    'load_catalog_section',
                    section_id=json_response['payload'][1][1]['sectionId'],
                    start_from=json_response['payload'][1][1]['nextFrom']
                )
        except (TypeError, IndexError):
            self._vk.logger.error("\n\nJSON RESPONSE:\n"+pformat(json_response))
            raise


    async def get_popular_iter(self, offset=0):
        """ Искать популярные аудиозаписи  (генератор)

        :param offset: смещение
        """
        offset_left = 0
        response = await self._vk.http.post(
            'https://vk.com/audio',
            data={
                'block':'tracks_chart',
                'section':'explore'
            }
        )
        json_response = json.loads(self._scrap_json(response.text))
        list = json_response['sectionData']['explore']['playlist']['list']
        section_id = json_response['sectionData']['explore']['sectionId'],
        start_from = json_response['sectionData']['explore']['nextFrom']

        clear_list = self._filter_by_id(list)

        if offset_left + len(clear_list) >= offset:
            if offset_left < offset:
                clear_list = clear_list[offset - offset_left:]

            for raw_audio in clear_list:
                yield self._wrap_audio(raw_audio)

        offset_left += len(clear_list)

        while True:
            json_response = await self._al_audio(
                'load_catalog_section',
                section_id=section_id,
                start_from=start_from
            )
            list = json_response['payload'][1][1]['playlist']['list']
            clear_list = self._filter_by_id(list)
            if not clear_list:
                break

            if offset_left + len(clear_list) >= offset:
                if offset_left < offset:
                    clear_list = clear_list[offset - offset_left:]

                for raw_audio in clear_list:
                    yield self._wrap_audio(raw_audio)

            offset_left += len(clear_list)
            section_id=json_response['payload'][1][1]['sectionId'],
            start_from=json_response['payload'][1][1]['nextFrom']

    async def get_news_iter(self,offset=0):
        """ Искать популярные аудиозаписи  (генератор)

        :param offset: смещение
        """

        offset_left = 0

        response = await self._vk.http.post(
            'https://vk.com/audio',
            data={
                'block':'new_songs',
                'section':'explore'
            }
        )
        json_response = json.loads(self._scrap_json(response.text))
        list = json_response['sectionData']['explore']['playlist']['list']
        section_id=json_response['sectionData']['explore']['sectionId'],
        start_from=json_response['sectionData']['explore']['nextFrom']

        clear_list = self._filter_by_id(list)
        if not clear_list:
            return

        if offset_left + len(clear_list) >= offset:
            if offset_left < offset:
                clear_list = clear_list[offset - offset_left:]

            for raw_audio in clear_list:
                yield self._wrap_audio(raw_audio)

        offset_left += len(clear_list)

        while True:
            json_response = await self._al_audio(
                'load_catalog_section',
                section_id=section_id,
                start_from=start_from
            )
            list = json_response['payload'][1][1]['playlist']['list']
            clear_list = self._filter_by_id(list)
            if not clear_list:
                break

            if offset_left + len(clear_list) >= offset:
                if offset_left < offset:
                    clear_list = clear_list[offset - offset_left:]

                for raw_audio in clear_list:
                    yield self._wrap_audio(raw_audio)

            offset_left += len(clear_list)
            section_id=json_response['payload'][1][1]['sectionId'],
            start_from=json_response['payload'][1][1]['nextFrom']

    async def get_audios_by_full_ids(self, full_ids):
        """ Получить аудиозапись по ID
        :param full_ids: [(<ownerID>, <audioID>, <actionHash>, <URLHash>)]
        """

        #split by 10 audios
        for ids_group in (full_ids[i:i + 10] for i in range(0, len(full_ids), 10)):

            json_response = await self._al_audio(
                'reload_audio',
                ids=','.join(
                    ('_'.join(id_tuple) for id_tuple in ids_group)
                )
            )
            last_request = time.time()

            raw_audios = json_response['payload'][1][0]
            for audio in map(self._wrap_audio, raw_audios):

                link = audio['URL']
                if 'audio_api_unavailable' in link:
                    link = decode_audio_url(link, self.user_id)

                if self.convert_m3u8_links and 'm3u8' in link:
                    link = RE_M3U8_TO_MP3.sub(r'\1/\2.mp3', link)
                audio['URL'] = link

                yield audio

    async def get_audios_by_ids(self, owner_id, audio_ids):
        """ Получить аудиозаписи по ID
        :param owner_id: ID владельца (отрицательные значения для групп)
        :param audio_id: ID аудио
        """

        response = await self._vk.method(
            "audio.get",
            values={
                "owner_id": owner_id,
                "audio_ids": audio_ids,
                "need_user": 0
            },
            raw=True
        )

        ids = self._scrap_id(response)

        async for audio in self.get_audios_by_full_ids(ids):
            yield audio

    async def get_audio_by_id(self, owner_id, audio_id, need_user = False):
        """ Получить аудиозаписи по ID
        :param owner_id: ID владельца (отрицательные значения для групп)
        :param audio_id: ID аудио

        https://web.archive.org/web/20161216125506/https://vk.com/dev/audio.get
        """

        response = await self._vk.http.get(
            f'https://m.vk.com/audio{owner_id}_{audio_id}'
        )

        ids = scrap_ids_from_html(
            response.text,
            filter_root_el={'class': 'basisDefault'}
        )
        audio = self.get_audios_by_full_ids(ids)

        try:
            return await audio.__anext__()
        except StopAsyncIteration:
            pass

    async def get_post_audio(self, owner_id, post_id):
        """ Получить список аудиозаписей из поста пользователя или группы
        :param owner_id: ID владельца (отрицательные значения для групп)
        :param post_id: ID поста
        """
        response = await self._vk.http.get(
            'https://m.vk.com/wall{}_{}'.format(owner_id, post_id)
        )

        ids = scrap_ids_from_html(
            response.text,
            filter_root_el={'class': 'audios_list'}
        )

        tracks = scrap_tracks(
            ids,
            self.user_id,
            http=self._vk.http,
            convert_m3u8_links=self.convert_m3u8_links
        )

        return tracks


def scrap_ids_from_html(html, filter_root_el=None):
    """ Парсинг списка хэшей аудиозаписей из html страницы """

    if filter_root_el is None:
        filter_root_el = {'id': 'au_search_items'}

    soup = BeautifulSoup(html, 'html.parser')
    ids = []

    root_el = soup.find(**filter_root_el)

    if root_el is None:
        raise ValueError('Could not find tg_vk_music_bot el for audio')

    playlist_snippets = soup.find_all('div', {'class': "audioPlaylistSnippet__list"})
    for playlist in playlist_snippets:
        playlist.decompose()

    for audio in root_el.find_all('div', {'class': 'audio_item'}):
        if 'audio_item_disabled' in audio['class']:
            continue

        data_audio = json.loads(audio['data-audio'])
        audio_hashes = data_audio[13].split("/")

        full_id = (
            str(data_audio[1]), str(data_audio[0]), audio_hashes[2], audio_hashes[5]
        )

        if all(full_id):
            ids.append(full_id)

    return ids


async def scrap_tracks(ids, user_id, http, convert_m3u8_links=True):
    tracks = []

    last_request = 0.0

    for ids_group in (ids[i:i + 10] for i in range(0, len(ids), 10)):
        delay = RPS_DELAY_RELOAD_AUDIO - (time.time() - last_request)

        if delay > 0:
            await asyncio.sleep(delay)

        result = (await http.post(
            'https://m.vk.com/audio',
            data={'act': 'reload_audio', 'ids': ','.join(('_'.join(i) for i in ids_group))}
        )).json()

        last_request = time.time()
        if result['data']:
            data_audio = result['data'][0]
            for audio in data_audio:
                artist = BeautifulSoup(audio[4], 'html.parser').text
                title = BeautifulSoup(audio[3].strip(), 'html.parser').text
                duration = audio[5]
                link = audio[2]

                if 'audio_api_unavailable' in link:
                    link = decode_audio_url(link, user_id)

                if convert_m3u8_links and 'm3u8' in link:
                    link = RE_M3U8_TO_MP3.sub(r'\1/\2.mp3', link)

                yield {
                    'ID': audio[0],
                    'OWNER_ID': audio[1],
                    'COVER_URL': audio[14].split(',') if audio[14] else [],
                    'URL': link,

                    'PERFORMER': artist,
                    'TITLE': title,
                    'DURATION': duration,
                }


def scrap_albums(html):
    """ Парсинг списка альбомов из html страницы """

    soup = BeautifulSoup(html, 'html.parser')
    albums = []

    for album in soup.find_all('div', {'class': 'audioPlaylistsPage__item'}):

        link = album.select_one('.audioPlaylistsPage__itemLink')['href']
        full_id = tuple(int(i) for i in RE_ALBUM_ID.search(link).groups())
        access_hash = RE_ACCESS_HASH.search(link)

        stats_text = album.select_one('.audioPlaylistsPage__stats').text

        # "1 011 прослушиваний"
        try:
            plays = int(stats_text.rsplit(' ', 1)[0].replace(' ', ''))
        except ValueError:
            plays = None

        albums.append({
            'id': full_id[1],
            'owner_id': full_id[0],
            'url': 'https://m.vk.com/audio?act=audio_playlist{}_{}'.format(
                *full_id
            ),
            'access_hash': access_hash.group(1) if access_hash else None,

            'title': album.select_one('.audioPlaylistsPage__title').text,
            'plays': plays
        })

    return albums

if __name__ == "__main__":

    loop = asyncio.get_event_loop()
    async def test_lock():
        lock = MyActLock(2)
        async def do_req():
            async with lock:
                print("enter")
                await asyncio.sleep(2)
                raise Exception('test raise')
                print("exit")

        await asyncio.gather(
            do_req(),
            do_req(),
            do_req()
        )
        for i in range(3):
            await do_req()

    import tg_lib
    from configparser import ConfigParser
    CONFIGS = ConfigParser()
    CONFIGS.read("config.ini")
    vk_session = AsyncVkApi(
        login=CONFIGS['vk']['login'],
        password=CONFIGS['vk']['password'],
        auth_handler=tg_lib.auth_handler,
        loop=loop
    )
    vk_session.sync_auth()
    vk_audio = AsyncVkAudio(vk_session)#"""

    async def find_rps():
        def unwrap_audio(audio):
            raw = [None]*len(AUDIO_ITEM)
            for item in audio:
                raw[AUDIO_ITEM_INDEX[item]] = audio[item]
            return raw
        time_start = time.time()

        act = 'reload_audio'
        lock = MyActLock(RPS_DELAY[act])
        query = await vk_audio.search("lizer", 45)
        for i, audio in enumerate(query):
            raw_audio = unwrap_audio(audio)
            ids = vk_audio._scrap_id([raw_audio])
            async with lock:
                response = await vk_audio._vk.http.post(
                    'https://vk.com/al_audio.php',
                    data={
                        'al': 1,
                        'act': act,
                        'ids':'_'.join(ids[0])
                    }
                )
            json_response = json.loads(response.text.replace('<!--', ''))
            print(i)
            pprint(json_response, depth = 3)
            if(json_response['payload'][0] == 8):break

    loop.run_until_complete(test_lock())
