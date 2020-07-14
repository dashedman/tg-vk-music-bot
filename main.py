import asyncio
import sqlite3
import time
import re
import argparse
import json
import sys
import os
import html
import ssl
import logging

from pprint import pprint, pformat
from collections import namedtuple, deque
from copy import deepcopy
from functools import partial
from random import randint

#ssl generate lib
from OpenSSL import crypto

#import requests
#asynchronious requests-like
from h11._util import RemoteProtocolError
from requests.exceptions import ConnectionError
import requests_async as requests

#vk_api...
from vk_api import VkApi
from vk_api.exceptions import AccessDenied
from async_extend import AsyncVkApi, AsyncVkAudio

#from vk_api.audio import VkAudio
from audio import VkAudio

#asynchronious flask-like
from sanic import Sanic
from sanic.response import json as sanic_json

#my local lib
import tg_lib
from tg_lib import DictionaryBomb
from ui_constants import *

"""
Create botdate.ini
Example:

1234567890:AaBbCcDdEeFfGgHhIiJjKkLL123456
my-domen.webhook.com
0.0.0.0
+71234567890
my_vk_password

"""
#constants
file_log = logging.FileHandler("botlogs.log")
console_out = logging.StreamHandler()

logging.basicConfig(
    handlers=(file_log, console_out),
    format='[%(asctime)s | %(levelname)s] %(name)s: %(message)s',
    datefmt='%a %b %d %H:%M:%S %Y',
    level=logging.INFO)
BOTLOG = logging.getLogger("bot")

with open("botdata.ini","r") as f:
    TG_TOKEN = f.readline()[:-1]
    WEBHOOK_DOMEN = f.readline()[:-1]
    HOST_IP = f.readline()[:-1]
    VK_LOGIN = f.readline()[:-1]
    VK_PASSWORD = f.readline()[:-1]

PORT = os.environ.get('PORT') or 88

TG_URL = "https://api.telegram.org/bot"+ TG_TOKEN +"/"
TG_SHELTER = -479340226
WEBHOOK_URL = f"https://{WEBHOOK_DOMEN}/{TG_TOKEN}/"

PKEY_FILE = "bot.pem"
KEY_FILE = "bot.key"
CERT_FILE = "bot.crt"
CERT_DIR = ""
SELF_SSL = True

MEGABYTE_SIZE = 1<<20
MUSIC_LIST_LENGTH = 2
MUSICLIST_CACHE= {}
TRACK_CACHE= {}
IS_DOWNLOAD = set()
CONNECT_COUNTER = 0
AD_COOLDOWN = 25

#functions

#self-ssl
def create_self_signed_cert(cert_dir):
    k = crypto.PKey()
    k.generate_key(crypto.TYPE_RSA, 1024)   #  размер может быть 2048, 4196

    #  Создание сертификата
    cert = crypto.X509()
    cert.get_subject().C = "RU"   #  указываем свои данные
    cert.get_subject().ST = "Saint-Petersburg"
    cert.get_subject().L = "Saint-Petersburg"   #  указываем свои данные
    cert.get_subject().O = "musicforus"   #  указываем свои данные
    cert.get_subject().CN = WEBHOOK_DOMEN   #  указываем свои данные
    cert.set_serial_number(1)
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(365*24*60*60)   #  срок "жизни" сертификата
    cert.set_issuer(cert.get_subject())
    cert.set_pubkey(k)
    cert.sign(k, 'SHA256')


    with open(os.path.join(cert_dir, CERT_FILE), "w") as f:
        f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert).decode("ascii"))

    with open(os.path.join(cert_dir, KEY_FILE), "w") as f:
        f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k).decode("ascii"))

    return crypto.dump_certificate(crypto.FILETYPE_PEM, cert).decode("ascii")

#cache functions
def get_cache(cache, key, current_page):
    cache[key][0].replant(time.time()+60*5)
    return cache[key][1]

async def caching_list(vk_audio, request):
    if request in MUSICLIST_CACHE: return
    #bomb on 5 minutes
    bomb = DictionaryBomb(MUSICLIST_CACHE, request, time.time()+60*5)

    if request == "!popular":
        generator = vk_audio.get_popular_iter()
    elif request == "!new_songs":
        generator = vk_audio.get_news_iter()
    else:
        generator = vk_audio.search_iter(request)

    musiclist = []
    MUSICLIST_CACHE[request] = (bomb, musiclist)

    musiclist.append(await generator.__anext__())
    for i in range(98):
        try:
            next_track = await generator.__anext__()
            if next_track == musiclist[0]:break
            musiclist.append(next_track)
        except StopAsyncIteration:
            break

    asyncio.create_task(bomb.plant())


#tg send functions
async def setWebhook(url='', certificate=None):
    await requests.post(
        TG_URL + 'setWebhook',
        data = {'url':url},
        files = {'certificate':certificate} if certificate else None,
        timeout=None
    )

async def getWebhookInfo():
    return await requests.post(TG_URL + 'getWebhookInfo', timeout=None)

async def sendMessage(chat_id, text, replay_message_id = None, **kwargs):
    data = {
        'chat_id':chat_id,
        'text': text
    }

    if replay_message_id:
        data['reply_to_message_id'] = replay_message_id

    data.update(kwargs)

    response = await requests.post(TG_URL + 'sendMessage', json = data, timeout=None)
    r = response.json()

    if not r['ok']:
        raise Exception(f"bad Message: {r}")
    return r['result']

async def sendKeyboard(chat_id, text, keyboard, replay_message_id = None, **kwargs):
    if replay_message_id:
        data = {
            'chat_id':chat_id,
            'text': text,
            'reply_to_message_id': replay_message_id,
            'reply_markup': keyboard
        }
    else:
        data = {
            'chat_id':chat_id,
            'text': text,
            'reply_markup': keyboard
        }
    data.update(kwargs)

    response = await requests.post(TG_URL + 'sendMessage', json = data, timeout=None)
    r = response.json()

    if not r['ok']:
        BOTLOG.info(pformat(r))
        pprint(data)
        if r['error_code'] != 400:
            raise Exception(f"bad Keyboard: {r}\n")
        else: return
    return r['result']

async def editKeyboard(chat_id, message_id, keyboard):
    data = {
        'chat_id':chat_id,
        'message_id': message_id,
        'reply_markup': keyboard
    }

    response = await requests.post(TG_URL + 'editMessageReplyMarkup', json = data, timeout=None)
    r = response.json()

    if not r['ok']:
        if r['error_code'] != 400:
            raise Exception(f"bad Keyboard edit: {r}")
        else: return
    return r['result']

async def sendAudio(chat_id, file = None, url = None, telegram_id = None, **kwargs):
    files = None
    if file:
        data = {
            'chat_id':chat_id
        }
        files = {'audio':file}
    elif url != None:
        data = {
            'chat_id':chat_id,
            'audio': url
        }
    elif telegram_id != None:
        data = {
            'chat_id':chat_id,
            'audio': telegram_id
        }
    else:
        raise Exception("Bad audio path!")

    data.update(kwargs)
    response = await requests.post(TG_URL + 'sendAudio', data = data, files = files, timeout=None)
    r = response.json()
    if not r['ok']:
        raise Exception(f"bad Audio: {r}")
    return r['result']

#msg demon-worker functions
async def send_error(result, err):
    BOTLOG.info(f"Поймал чипалах :с\nСоединений: {CONNECT_COUNTER}")
    while True:
        try:
            await sendMessage(TG_SHELTER, f"Поймал чипалах :с\nСоединений: {CONNECT_COUNTER}\nError: {repr(err)}")
        except Exception:
            await asyncio.sleep(60)
        else:
            break

async def seek_and_send(vk_audio, db, msg, request = None):
    if not request: request = msg['text']

    if len(request.encode("utf-8")) > 59:
        await sendMessage(msg['chat']['id'],
                            f'Слишком большой запрос :с\n',
                            msg['message_id'])
        return
    #seek music in vk
    current_page = 1

    if request in MUSICLIST_CACHE and current_page*MUSIC_LIST_LENGTH <= len(MUSICLIST_CACHE[request][1]):
        musiclist = get_cache(MUSICLIST_CACHE, request, current_page)[(current_page-1)*9:current_page*9]
        NEXT_PAGE_FLAG = True
        if len(musiclist)<MUSIC_LIST_LENGTH or current_page == 11: NEXT_PAGE_FLAG = False

    else:
        while True:
            try:
                res_generator = vk_audio.search_iter(request)
                musiclist, NEXT_PAGE_FLAG = await tg_lib.get_music_list(res_generator, current_page, MUSIC_LIST_LENGTH)
            except ConnectionError:
                asyncio.sleep(1)
            else:
                break

        if not musiclist:
            await sendMessage(msg['chat']['id'],
                                'По вашему запросу ничего не нашлось :c',
                                msg['message_id'])
            return

        if NEXT_PAGE_FLAG: asyncio.create_task(caching_list(vk_audio, request))
    #construct inline keyboard for list
    inline_keyboard = tg_lib.get_inline_keyboard(musiclist, request, NEXT_PAGE_FLAG, current_page)

    #send answer
    await sendKeyboard(msg['chat']['id'], \
                        msg['text'], \
                        {'inline_keyboard':inline_keyboard}, \
                        msg['message_id'],
                        disable_web_page_preview = True)

async def send_popular(vk_audio, db, msg):
    #seek music in vk
    current_page = 1
    request = "!popular"

    if request in MUSICLIST_CACHE and current_page*MUSIC_LIST_LENGTH <= len(MUSICLIST_CACHE[request][1]):
        musiclist = get_cache(MUSICLIST_CACHE, request, current_page)[(current_page-1)*9:current_page*9]
        NEXT_PAGE_FLAG = True
        if len(musiclist)<MUSIC_LIST_LENGTH or current_page == 11: NEXT_PAGE_FLAG = False
    else:
        while True:
            try:
                res_generator = vk_audio.get_popular_iter()
                musiclist, NEXT_PAGE_FLAG = await tg_lib.get_music_list(res_generator, current_page, MUSIC_LIST_LENGTH)
            except ConnectionError:
                asyncio.sleep(1)
            else:
                break
        if NEXT_PAGE_FLAG: asyncio.create_task(caching_list(vk_audio, request))

    #construct inline keyboard for list
    inline_keyboard = tg_lib.get_inline_keyboard(musiclist, request, NEXT_PAGE_FLAG, current_page)

    #send answer
    await sendKeyboard(msg['chat']['id'], \
                        msg['text'], \
                        {'inline_keyboard':inline_keyboard}, \
                        msg['message_id'])

async def send_new_songs(vk_audio, db, msg):
    #seek music in vk
    current_page = 1
    request = "!new_songs"

    if request in MUSICLIST_CACHE and current_page*MUSIC_LIST_LENGTH <= len(MUSICLIST_CACHE[request][1]):
        musiclist = get_cache(MUSICLIST_CACHE, request, current_page)[(current_page-1)*9:current_page*9]
        NEXT_PAGE_FLAG = True
        if len(musiclist)<MUSIC_LIST_LENGTH or current_page == 11: NEXT_PAGE_FLAG = False
    else:
        while True:
            try:
                res_generator = vk_audio.get_news_iter()
                musiclist, NEXT_PAGE_FLAG = await tg_lib.get_music_list(res_generator, current_page, MUSIC_LIST_LENGTH)
            except ConnectionError:
                asyncio.sleep(1)
            else:
                break
        if NEXT_PAGE_FLAG: asyncio.create_task(caching_list(vk_audio, request))

    #construct inline keyboard for list
    inline_keyboard = tg_lib.get_inline_keyboard(musiclist, request, NEXT_PAGE_FLAG, current_page)

    #send answer
    await sendKeyboard(msg['chat']['id'], \
                        msg['text'], \
                        {'inline_keyboard':inline_keyboard}, \
                        msg['message_id'])

async def check_advertisement(db, msg):

    count = tg_lib.get_chat_counter(db, msg['chat']['id'])
    if count <= 1:
        count = AD_COOLDOWN
        tg_lib.put_chat_counter(db, msg['chat']['id'], count)

        ad = tg_lib.get_ad(db)
        if not ad: return
        ad_id, ad_text, ad_json_list, ad_counter = ad

        if ad_counter > 1:
            tg_lib.decrement_ad(db, ad_id, ad_counter-1)
        else:
            tg_lib.delete_ad(db, ad_id)
        inline_keyboard = [[{
                             'text':'⤵️ Show',
                             'callback_data': f'e@!ad@{ad_id}'
                            }]]

        await sendMessage(
            msg['chat']['id'],
            ad_text,
            disable_web_page_preview=True,
            parse_mode='markdownv2',
            reply_markup={'inline_keyboard': inline_keyboard},
            reply_to_message_id = msg['message_id']
        )


    else:
        count -= 1
        tg_lib.put_chat_counter(db, msg['chat']['id'], count)


#asynchronious workers
async def workerMsg(vk_audio, db, msg):
    if 'text' in msg:
        if msg['text'][0] == '/':
            #if command
            await command_demon(vk_audio, db, msg)
        elif msg['text'] in KEYBOARD_COMMANDS:
            #if keyboard
            await command_demon(vk_audio, db, msg, KEYBOARD_COMMANDS[msg['text']])
        else:
            #just message
            if tg_lib.all_mode_check(db, msg['chat']['id']):
                BOTLOG.info(f"Message: {msg['text']}")
                await seek_and_send(vk_audio, db, msg)


async def workerCallback(vk_audio, db, callback):
    data = callback['data'].split('@')
    BOTLOG.info(f"Callback data: {data}")
    command, data = data[0], data[1:]

    if command == 'd' :
        audio_id = data[0]+'_'+data[1]

        asyncio.create_task(check_advertisement(db, callback['message']))

        while audio_id in IS_DOWNLOAD:
            await asyncio.sleep(0.07)
        #check audio in old loads
        if audio_data := tg_lib.db_get_audio(db, audio_id):
            telegram_id, audio_size = audio_data
            #send id from old audio in telegram
            await sendAudio(callback['message']['chat']['id'], \
                            telegram_id = telegram_id,
                            caption=f'{audio_size:.2f} MB t\n_via MusicForUs\_bot_'.replace('.','\.'),
                            parse_mode='markdownv2')
        else:
            IS_DOWNLOAD.add(audio_id)

            new_audio = await vk_audio.get_audio_by_id(*data)
            """while True:
                try:
                    new_audio = await vk_audio.get_audio_by_id(*data)
                except ConnectionError:
                    await asyncio.sleep(1)
                else:
                    break"""

            #download audio
            response = await requests.head(new_audio['url'])
            audio_size = int(response.headers.get('content-length', 0)) / MEGABYTE_SIZE
            if audio_size >= 50:
                duration = time.gmtime(new_audio['duration'])
                await sendMessage(
                    callback['message']['chat']['id'],
                    html.unescape(f"{new_audio['artist']} - {new_audio['title']} ({duration.tm_min}:{duration.tm_sec:02})\nThis audio file size is too large :c".replace("$#","&#"))
                )
                IS_DOWNLOAD.discard(audio_id)
                return

            while True:
                try:
                    response = await requests.get(new_audio['url'])
                except RemoteProtocolError:
                    await asyncio.sleep(0)
                else:
                    break


            #send new audio file
            response = await sendAudio(callback['message']['chat']['id'],
                                        file = response.content,
                                        title = html.unescape(new_audio['title']),
                                        performer = html.unescape(new_audio['artist']),
                                        caption=f'{audio_size:.2f} MB f\n_via MusicForUs\_bot_'.replace('.','\.'),
                                        parse_mode='markdownv2')

            #multiline comment
            '''
            response = await sendAudio(callback['message']['chat']['id'],
                                        url = new_audio['url'],
                                        #mime_type = 'audio/mp3',
                                        title = new_audio['title'],
                                        performer = new_audio['artist'],
                                        caption='{:.2f} MB u\n_via MusicForUs\_bot_'.format(audio_size).replace('.','\.'),
                                        parse_mode='markdownv2')
            '''

            #save new audio in db
            tg_lib.db_put_audio( db, \
                                  audio_id, \
                                  response['audio']['file_id'],
                                  audio_size)
            IS_DOWNLOAD.discard(audio_id)

    if command == 'e':

        request = data[0]
        current_page = int(data[1])# or ad_id for ad

        if request in MUSICLIST_CACHE and current_page*MUSIC_LIST_LENGTH <= len(MUSICLIST_CACHE[request][1]):
            musiclist = get_cache(MUSICLIST_CACHE, request, current_page)[(current_page-1)*9:current_page*9]
            NEXT_PAGE_FLAG = True
            if len(musiclist)<MUSIC_LIST_LENGTH or current_page == 11: NEXT_PAGE_FLAG = False
        else:
            while True:
                try:
                    if request == "!ad":
                        res_generator = tg_lib.get_ad_generator(vk_audio, db, current_page)#this is ad_id
                    elif request == "!popular":
                        res_generator = vk_audio.get_popular_iter(offset=current_page*MUSIC_LIST_LENGTH )
                    elif request == "!new_songs":
                        res_generator = vk_audio.get_news_iter(offset=(current_page-1)*MUSIC_LIST_LENGTH )
                    else:
                        res_generator = vk_audio.search_iter(request, offset=(current_page-1)*MUSIC_LIST_LENGTH )

                    musiclist, NEXT_PAGE_FLAG = await tg_lib.get_music_list(res_generator, current_page, MUSIC_LIST_LENGTH)
                except ConnectionError:
                    asyncio.sleep(1)
                else:
                    break
            if request != "!ad" and NEXT_PAGE_FLAG: asyncio.create_task(caching_list(vk_audio, request))

        #construct inline keyboard for list
        if request != "!ad":
            inline_keyboard = tg_lib.get_inline_keyboard( musiclist, request, NEXT_PAGE_FLAG, current_page)
        else:
            inline_keyboard = []
            if musiclist:
                for music in musiclist:
                    duration = time.gmtime(music['duration'])
                    inline_keyboard.append([{
                        'text': html.unescape(f"{music['artist']} - {music['title']} ({duration.tm_min}:{duration.tm_sec:02})".replace("$#","&#")),
                        'callback_data':f"d@{music['owner_id']}@{music['id']}"
                    }])
                inline_keyboard.append([{
                    'text': '⤴️ Hide',
                    'callback_data': f'h@{request}@{current_page}'#this is ad_id
                }])
            else:
                inline_keyboard.append([{
                    'text': '♻️ Ad is gone',
                    'callback_data': f'pass@'#this is ad_id
                }])

        #send answer
        await editKeyboard(callback['message']['chat']['id'], \
                            callback['message']['message_id'], \
                            {'inline_keyboard':inline_keyboard})

    if command == 'h':
        request = data[0]
        current_page = int(data[1])#or ad_id if request == '!ad'

        inline_keyboard = [[{
                             'text':'⤵️ Show',
                             'callback_data': f'e@{request}@{current_page}'
                            }]]
        await editKeyboard(callback['message']['chat']['id'], \
                            callback['message']['message_id'], \
                            {'inline_keyboard':inline_keyboard})

    if command == "pass":
        pass


#demon
async def command_demon(vk_audio, db, msg, command = None):
    if not command: command = msg['text'][1:]

    mail_id = command.find('@')
    if mail_id > -1:
        space_id = command.find(' ')
        if space_id > mail_id or space_id == -1:
            command = command[:mail_id+15].lower().replace('@musicforus_bot','')+command[mail_id+15:]


    BOTLOG.info(f"Command: /{command}")

    if command == 'start':
        if 'username' in msg['from']:
            await sendKeyboard(msg['chat']['id'], \
                            f"Keyboard for @{msg['from'].get('username') or msg['from']['id']}",
                            {'keyboard': MAIN_KEYBOARD,
                             'resize_keyboard': True,
                             'one_time_keyboard': True,
                             'selective': True})
        else:
            await sendKeyboard(msg['chat']['id'], \
                            f"Hi!",
                            {'keyboard': MAIN_KEYBOARD,
                             'resize_keyboard': True,
                             'one_time_keyboard': True})
    elif command[:2] == 'f ':
        await seek_and_send(vk_audio, db, msg, command[2:])
    elif command[:5] == 'find ':
        await seek_and_send(vk_audio, db, msg, command[5:])
    elif command == 'popular' or command == 'chart':
        await send_popular(vk_audio, db, msg)
    elif command == 'new_songs':
        await send_new_songs(vk_audio, db, msg)
    elif command == 'help':
        await sendMessage(msg['chat']['id'], \
                            HELP_TEXT)
    elif command == 'quick':
        await sendMessage(msg['chat']['id'], \
                            QUICK_TEXT)
    elif command == 'about':
        await sendMessage(msg['chat']['id'], \
                            ABOUT_TEXT)
    elif command == 'settings':
        tmp_settings_keyboard = deepcopy(SETTINGS_KEYBOARD)
        tmp_settings_keyboard.append([{
            'text':'🙈 Listen only to commands'
            if tg_lib.all_mode_check(db, msg['chat']['id'])
            else '🐵 Listen to all message'
        }])

        await sendKeyboard(msg['chat']['id'],
                            f"{msg['text']} for @{msg['from'].get('username') or msg['from']['id']}",
                            {'keyboard': tmp_settings_keyboard,
                             'resize_keyboard': True,
                             'selective':True })

    elif command == 'all_mode_on':
        tg_lib.all_mode_on(db, msg['chat']['id'])
        tmp_settings_keyboard = deepcopy(SETTINGS_KEYBOARD)
        tmp_settings_keyboard.append([{'text':'🙈 Listen only to commands'
                                               if tg_lib.all_mode_check(db, msg['chat']['id'])
                                               else '🐵 Listen to all message'}])

        await sendKeyboard(msg['chat']['id'],
                            f"Mode was changed via @{msg['from'].get('username') or msg['from']['id']} (ON)",
                            {'keyboard': tmp_settings_keyboard,
                             'resize_keyboard': True,
                             'selective':True })
    elif command == 'all_mode_off':
        tg_lib.all_mode_off(db, msg['chat']['id'])
        tmp_settings_keyboard = deepcopy(SETTINGS_KEYBOARD)
        tmp_settings_keyboard.append([{'text':'🙈 Listen only to commands'
                                               if tg_lib.all_mode_check(db, msg['chat']['id'])
                                               else '🐵 Listen to all message'}])

        await sendKeyboard(msg['chat']['id'],
                            f"Mode was changed via @{msg['from'].get('username') or msg['from']['id']} (OFF)",
                            {'keyboard': tmp_settings_keyboard,
                             'resize_keyboard': True,
                             'selective':True })

    #commands for admins
    elif msg['chat']['id'] == TG_SHELTER:
        if  command == 'advertisement':
            ad = tg_lib.get_ad(db)

            if not ad:
                await sendMessage(
                    msg['chat']['id'],
                    "Актуальной рекламы нет"
                )
                return
            ad_id, ad_text, ad_json_list, ad_counter = ad

            inline_keyboard = [[{
                                 'text':'⤵️ Show',
                                 'callback_data': f'e@!ad@{ad_id}'
                                }]]

            await sendMessage(
                msg['chat']['id'],
                f"Для Рекламы №{ad_id} Осталось {ad_counter-1} размещений"
            )
            await sendMessage(
                msg['chat']['id'],
                ad_text,
                disable_web_page_preview=True,
                parse_mode='markdownv2',
                reply_markup={'inline_keyboard': inline_keyboard},
                reply_to_message_id = msg['message_id']
            )
            if ad_counter > 1:
                tg_lib.decrement_ad(db, ad_id, ad_counter-1)
            else:
                tg_lib.delete_ad(db, ad_id)

        elif command[:5] == "addad":
            data = command[6:].split("\n")

            #get data about ad
            counter = int(data[0])
            album_url = data[1]
            caption = '\n'.join(data[2:])

            #get playlist ids
            matches = re.search(r"=audio_playlist(.*?)_(.*)(&|%)?", album_url)
            owner_id = matches.group(1)
            album_id = matches.group(2)
            matches = re.search(r"%2F(.*)&?", album_url)
            access_hash = None
            if matches: access_hash = matches.group(1)

            #get three or less track from album
            try:
                generator = vk_audio.get_iter(owner_id = owner_id, album_id = album_id, access_hash = access_hash)
                tracklist, NPF = await tg_lib.get_music_list(generator, list_length = 3)
            except AccessDenied:
                response = await sendMessage(
                    msg['chat']['id'],
                    f"Album access denied for {owner_id}_{album_id} AH: {access_hash}"
                )
                return

            BOTLOG.info(f"Loading audios for ad")
            for track in tracklist:
                audio_id = f"{track['owner_id']}_{track['id']}"
                #check audio in old loads
                if audio_data := tg_lib.db_get_audio(db, audio_id):
                    continue

                #download audio
                response = await requests.head(track['url'])
                track_size = int(response.headers.get('content-length', 0)) / MEGABYTE_SIZE
                if track_size >= 50:
                    BOTLOG.info(html.unescape(f"{track['artist']}-{track['title']} to big: {track_size} MB"))
                    track = None
                    continue
                response = await requests.get(track['url'])

                BOTLOG.info(html.unescape(f"Ready Track: {track['artist']}-{track['title']} {track_size} MB"))
                #send new audio file
                response = await sendAudio(
                    msg['chat']['id'],
                    file = response.content,
                    title = html.unescape(track['title']),
                    performer = html.unescape(track['artist']),
                    caption=f'{track_size:.2f} MB f\n_via MusicForUs\_bot_'.replace('.','\.'),
                    parse_mode='markdownv2'
                )

                #save new audio in db
                tg_lib.db_put_audio(
                    db,
                    audio_id,
                    response['audio']['file_id'],
                    track_size
                )

            #save ad
            while True:
                try:
                    tracklist.remove(None)
                except ValueError:
                    break

            tg_lib.put_ad(
                db, None, caption,
                json.dumps(tracklist), counter
            )

            #show new ad
            db.cursor.execute(
                """SELECT * FROM ad_buffer
                WHERE track_list=?"""
                , (json.dumps(tracklist), ))
            ad_id, ad_text, ad_list, ad_counter = db.cursor.fetchone()



            inline_keyboard = [[{
                'text':'⤵️ Show',
                'callback_data': f'e@!ad@{ad_id}'
            }]]
            try:
                await sendMessage(
                    msg['chat']['id'],
                    caption,
                    parse_mode = 'markdownv2',
                    disable_web_page_preview=True,
                    reply_markup = {'inline_keyboard': inline_keyboard},
                    reply_to_message_id = msg['message_id']
                )

                await sendMessage(
                    msg['chat']['id'],
                    f"Установлна реклама №{ad_id} на {ad_counter} размещений.",
                )
            except Exception as err:
                await sendMessage(
                    msg['chat']['id'],
                    "Ошибка"+repr(err)
                )
                tg_lib.delete_ad(
                    db, ad_id
                )
        elif command[:6] == "delad ":
            try:
                ad_id = int(command[6:])
            except Exception as err:
                await sendMessage(
                    msg['chat']['id'],
                    f"Invalid command: {repr(err)}",
                )
            tg_lib.delete_ad(
                db, ad_id
            )
            await sendMessage(
                msg['chat']['id'],
                f"Ad {ad_id} deleted success!",
            )
        elif command == "adlist":

            db.cursor.execute("""SELECT * FROM ad_buffer""")
            str_list=""
            for ad in db.cursor.fetchall():
                str_list += f"№{ad[0]} [{ad[3]}]: {ad[1][:40]}\n"
            await sendMessage(
                msg['chat']['id'],
                f"Ads:\n"+str_list,
            )
        elif command == "cache":
            str_list=""
            for it, request in enumerate(MUSICLIST_CACHE):
                str_list += f"{it}. [{request}]: len={len(MUSICLIST_CACHE[request][1])} etime={MUSICLIST_CACHE[request][0].timer}\n"
            await sendMessage(
                msg['chat']['id'],
                f"Time now: {time.time()}\nMusic list cashe({len(MUSICLIST_CACHE)}):\n"+str_list,
            )


async def result_demon(vk_audio, db, result):
    global CONNECT_COUNTER
    tid = randint(1,1000)
    CONNECT_COUNTER += 1
    try:
        #just message
        if 'message' in result:
            await workerMsg(vk_audio, db, result['message'])
        #callback
        elif 'callback_query' in result:
            await workerCallback(vk_audio, db, result['callback_query'])
        elif 'edited_message' in result:
            pass

    except Exception as err:
        asyncio.create_task(send_error(result,err))
        BOTLOG.exception(f"Error ocured {err}")
    finally:
        CONNECT_COUNTER -= 1
    return


#listeners
#~~flask~~ ~~vibora~~ sanic, requests
async def WHlistener(vk_audio, db):
    #asyncio.get_event_loop().set_debug(True)

    BOTLOG.info(f"Set Webhook...")
    if SELF_SSL:
        #create ssl for webhook
        create_self_signed_cert(CERT_DIR)
        with open(os.path.join(CERT_DIR, CERT_FILE), "rb") as f:
            await setWebhook(WEBHOOK_URL, certificate = f)

        context = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(
            os.path.join(CERT_DIR, CERT_FILE),
            keyfile=os.path.join(CERT_DIR, KEY_FILE)
        )

    else:
        await setWebhook(WEBHOOK_URL)

    response = (await getWebhookInfo()).json()
    if not response['ok']:
        BOTLOG.info("Webhook wasn't setted")
        BOTLOG.debug(pformat(response))
        BOTLOG.info(f"Shut down...")
        return

    BOTLOG.info("New webhook:")
    BOTLOG.info(f"\tUrl: {response['result']['url']}")
    BOTLOG.info(f"\tPending update: {response['result']['pending_update_count']}")
    BOTLOG.info(f"\tCustom certificate: {response['result']['has_custom_certificate']}")

    if response['result']['url'] != WEBHOOK_URL:
        BOTLOG.info(f"WebHook wasn't setted!")
        BOTLOG.info(f"Shut down...")
        return



    app_listener = Sanic(__name__)

    @app_listener.route('/{}/'.format(TG_TOKEN), methods = ['GET','POST'])
    async def receive_update(request):
        if request.method == "POST":
            await result_demon(vk_audio, db, request.json)
        return sanic_json({"ok": True})

    BOTLOG.info(f"Listening...")
    server = app_listener.create_server(
        host = HOST_IP,
        port = PORT,
        return_asyncio_server=True,
        access_log = False,
        ssl = context if SELF_SSL else None
    )
    asyncio.create_task(server)


#requests only
async def LPlistener(vk_audio, db):
    LONGPOLING_OFFSET = 0
    LONGPOLING_DELAY = 3

    #offwebhook
    await setWebhook()

    #start listen
    BOTLOG.info(f"Listening...")
    while True:

        #get new messages
        success = False

        while not success:
            try:
                response = await requests.get(TG_URL + 'getUpdates',params =  {"offset":LONGPOLING_OFFSET}, timeout=None)
                r = response.json()
            except TimeoutError:
                pass
            else:
                success = r['ok']
            await asyncio.sleep(LONGPOLING_DELAY)

        #go to proceed all of them
        for result in r['result']:
            LONGPOLING_OFFSET = max(LONGPOLING_OFFSET,result['update_id'])+1

            asyncio.create_task(result_demon(vk_audio, db, result))

#start func
def start_bot(WEB_HOOK_FLAG = True):

    BOTLOG.info(f"Start...")
    #print important constants
    BOTLOG.info(f"""
            {TG_TOKEN=}
            {VK_LOGIN=}
            {VK_PASSWORD=}
            {TG_URL=}
            {TG_SHELTER=}
            {WEB_HOOK_FLAG=}
            {WEBHOOK_DOMEN=}
            {WEBHOOK_URL=}
            {SELF_SSL=}
            {HOST_IP=}
            {PORT=}""")

    try:
        #database loading
        BOTLOG.info(f"Database loading...")
        db_connect = sqlite3.connect("botbase.db")
        db_cursor = db_connect.cursor()

        db = namedtuple('Database', 'conn cursor')(conn = db_connect, cursor = db_cursor)
        #if new database

        #audios table
        db_cursor.execute(
            """CREATE TABLE IF NOT EXISTS audios
            (id TEXT PRIMARY KEY,
            telegram_id TEXT NOT NULL,
            audio_size FLOAT NOT NULL)""")

        #all_mode table
        db_cursor.execute(
            """CREATE TABLE IF NOT EXISTS chats
            (id TEXT PRIMARY KEY,
            mode BOOL NOT NULL,
            ad_counter INT NOT NULL DEFAULT 25)""")

        #adwertisiment table
        db_cursor.execute(
            """CREATE TABLE IF NOT EXISTS ad_buffer
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
            caption TEXT NOT NULL,
            track_list TEXT NOT NULL,
            counter INT NOT NULL)""")

        db_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        BOTLOG.info("TABLES:")
        for table in db_cursor.fetchall():
            BOTLOG.info(f"\t{table[0]}")

        loop = asyncio.get_event_loop()
        #autetifications in vk
        BOTLOG.info(f"Vk autentification...")
        vk_session = AsyncVkApi(VK_LOGIN, VK_PASSWORD, auth_handler=tg_lib.auth_handler, loop = loop)
        vk_session.auth()

        #vk audio class for fetching music
        vk_audio = AsyncVkAudio(vk_session)

        #pick type of listener and run
        loop.create_task((WHlistener if WEB_HOOK_FLAG else LPlistener)(vk_audio, db))
        loop.run_forever()

    except Exception as err:
        #Any error should send ping message to developer
        BOTLOG.info(f"я упал :с")
        while True:
            try:
                asyncio.run(sendMessage(TG_SHELTER, "я упал :с"))
            except Exception:
                time.sleep(60)
            else:
                break

        db_connect.close()
        loop.close()
        BOTLOG.exception(f"Error ocured {err}")
        raise(err)
    except BaseException as err:
        #Force exit with ctrl+C
        db_connect.close()
        loop.close()
        BOTLOG.info(f"Force exit. {err}")

if __name__ == "__main__":
    #parse args

    parser = argparse.ArgumentParser()
    parser.add_argument('-wh', action="store", dest="webhook_on", default=1, type=int)
    parser.add_argument('-p', action="store", dest="port", default=None, type=int)
    parser.add_argument('-i', action="store", dest="ip", default=None)
    parser.add_argument('-d', action="store", dest="domen", default=None)
    parser.add_argument('-s', action="store", dest="ssl", default=None, type=int)
    args = parser.parse_args()

    if args.port: PORT = args.port
    if args.ip: HOST_IP = args.ip
    if args.domen:
        WEBHOOK_DOMEN = args.domen
        WEBHOOK_URL = f"https://{WEBHOOK_DOMEN}/{TG_TOKEN}/"
    if args.ssl != None:
        SELF_SSL = bool(args.ssl)

    #if main then start bot
    start_bot(bool(args.webhook_on))
