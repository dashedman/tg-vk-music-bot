import asyncio
import sqlite3
import time
import re
import argparse
import json
import sys
import os
import html

from pprint import pprint
from collections import namedtuple, deque
from copy import deepcopy
from functools import partial

#ssl generate lib
from OpenSSL import crypto

#import requests
#asynchronious requests-like
from requests.exceptions import ConnectionError
import requests_async as requests

#vk_api...
from vk_api import VkApi
from async_extend import AsyncVkApi, AsyncVkAudio

#from vk_api.audio import VkAudio
from audio import VkAudio

#asynchronious flask-like
from sanic import Sanic
from sanic.response import json as sanic_json

#my local lib
import tg_lib
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
with open("botdata.ini","r") as f:
    TG_TOKEN = f.readline()[:-1]
    WEBHOOK_DOMEN = f.readline()[:-1]
    HOST_IP = f.readline()[:-1]
    VK_LOGIN = f.readline()[:-1]
    VK_PASSWORD = f.readline()[:-1]

PORT = os.environ.get('PORT')

TG_URL = "https://api.telegram.org/bot"+ TG_TOKEN +"/"
TG_SHELTER = -479340226
WEBHOOK_URL = "https://"+ WEBHOOK_DOMEN +"/"+ TG_TOKEN +"/"

KEY_FILE = "bot.key"
CERT_FILE = "bot.pem"
CERT_DIR = "ssl_folder"
SELF_SSL = True

MEGABYTE_SIZE = 1<<20
MUSIC_LIST_LENGTH = 9
IS_DOWNLOAD = set()

#functions

#self-ssl
def create_self_signed_cert(cert_dir):
    k = crypto.PKey()
    k.generate_key(crypto.TYPE_RSA, 1024)   #  размер может быть 2048, 4196

    #  Создание сертификата
    cert = crypto.X509()
    cert.get_subject().C = "RU"   #  указываем свои данные
    cert.get_subject().L = "Moscow"   #  указываем свои данные
    cert.get_subject().O = "musicforus"   #  указываем свои данные
    cert.get_subject().CN = WEBHOOK_DOMEN   #  указываем свои данные
    cert.set_serial_number(1000)
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(10*365*24*60*60)   #  срок "жизни" сертификата
    cert.set_issuer(cert.get_subject())
    cert.set_pubkey(k)
    cert.sign(k, 'sha1')

    with open(os.path.join(cert_dir, CERT_FILE), "wb") as f:
        f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))

    with open(os.path.join(cert_dir, KEY_FILE), "wb") as f:
        f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k))

#tg send functions
async def setWebhook(url='', certificate=None):
    await requests.post(
        TG_URL + 'setWebhook',
        json = {'url':url},
        files = {'certificate':certificate} if certificate else None,
        timeout=None)

async def getWebhookInfo():
    return await requests.post(TG_URL + 'getWebhookInfo', timeout=None)

async def sendMessage(chat_id, text, replay_message_id = None):
    data = {
        'chat_id':chat_id,
        'text': text
    }

    if replay_message_id:
        data['reply_to_message_id'] = replay_message_id

    response = await requests.post(TG_URL + 'sendMessage', json = data, timeout=None)
    r = response.json()

    if not r['ok']:
        pprint(r)
        raise("no ok")
    return r['result']

async def sendKeyboard(chat_id, text, keyboard, replay_message_id = None):
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

    response = await requests.post(TG_URL + 'sendMessage', json = data, timeout=None)
    r = response.json()

    if not r['ok']:
        pprint(r)
        pprint(data)
        raise("no ok")
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
        pprint(r)
        pprint(data)
        raise("no ok")
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
        raise("Bad audio path!")

    data.update(kwargs)
    response = await requests.post(TG_URL + 'sendAudio', data = data, files = files, timeout=None)
    r = response.json()
    if not r['ok']:
        pprint(r)
        raise("no ok")
    return r['result']

#msg demon-worker functions
async def seek_and_send(vk_audio, db, msg, request = None):
    if not request: request = msg['text']
    #seek music in vk
    current_page = 1

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
    #construct inline keyboard for list
    inline_keyboard = tg_lib.get_inline_keyboard(musiclist, request, NEXT_PAGE_FLAG, current_page)

    #send answer
    await sendKeyboard(msg['chat']['id'], \
                        msg['text'], \
                        {'inline_keyboard':inline_keyboard}, \
                        msg['message_id'])

async def send_popular(vk_audio, db, msg):
    #seek music in vk
    current_page = 1

    while True:
        try:
            res_generator = vk_audio.get_popular_iter()
            musiclist, NEXT_PAGE_FLAG = await tg_lib.get_music_list(res_generator, current_page, MUSIC_LIST_LENGTH)
        except ConnectionError:
            asyncio.sleep(1)
        else:
            break

    #construct inline keyboard for list
    inline_keyboard = tg_lib.get_inline_keyboard(musiclist, "!popular", NEXT_PAGE_FLAG, current_page)

    #send answer
    await sendKeyboard(msg['chat']['id'], \
                        msg['text'], \
                        {'inline_keyboard':inline_keyboard}, \
                        msg['message_id'])

async def send_new_songs(vk_audio, db, msg):
    #seek music in vk

    current_page = 1

    while True:
        try:
            res_generator = vk_audio.get_news_iter()
            musiclist, NEXT_PAGE_FLAG = await tg_lib.get_music_list(res_generator, current_page, MUSIC_LIST_LENGTH)
        except ConnectionError:
            asyncio.sleep(1)
        else:
            break

    #construct inline keyboard for list
    inline_keyboard = tg_lib.get_inline_keyboard(musiclist, "!new_songs", NEXT_PAGE_FLAG, current_page)

    #send answer
    await sendKeyboard(msg['chat']['id'], \
                        msg['text'], \
                        {'inline_keyboard':inline_keyboard}, \
                        msg['message_id'])

async def command_demon(vk_audio, db, msg, command = None):
    if not command: command = msg['text'][1:]

    space_id = command.find(' ')
    if space_id == -1:
        command = command.lower().replace('@musicforus_bot','')
    else:
        command = command[:space_id].lower().replace('@musicforus_bot','')+command[space_id:]

    print(f'Command: /{command}')

    if command == 'start':
        await sendKeyboard(msg['chat']['id'], \
                            f"Keyboard for @{msg['from']['username']}",
                            {'keyboard': MAIN_KEYBOARD,
                             'resize_keyboard': True,
                             'one_time_keyboard': True,
                             'selective': True})
    if command[:2] == 'f ':
        await seek_and_send(vk_audio, db, msg, command[2:])
    if command[:5] == 'find ':
        await seek_and_send(vk_audio, db, msg, command[5:])
    if command == 'popular' or command == 'chart':
        await send_popular(vk_audio, db, msg)
    if command == 'new_songs':
        await send_new_songs(vk_audio, db, msg)
    if command == 'help':
        await sendMessage(msg['chat']['id'], \
                            HELP_TEXT)
    if command == 'quick':
        await sendMessage(msg['chat']['id'], \
                            QUICK_TEXT)
    if command == 'about':
        await sendMessage(msg['chat']['id'], \
                            ABOUT_TEXT)
    if command == 'settings':
        tmp_settings_keyboard = deepcopy(SETTINGS_KEYBOARD)
        tmp_settings_keyboard.append([{'text':'🙈 Listen only to commands'
                                               if tg_lib.all_mode_check(db, msg['chat']['id'])
                                               else '🐵 Listen to all message'}])

        await sendKeyboard(msg['chat']['id'],
                            f"{msg['text']} for @{msg['from']['username']}",
                            {'keyboard': tmp_settings_keyboard,
                             'resize_keyboard': True,
                             'selective':True })

    if command == 'all_mode_on':
        tg_lib.all_mode_on(db, msg['chat']['id'])
        tmp_settings_keyboard = deepcopy(SETTINGS_KEYBOARD)
        tmp_settings_keyboard.append([{'text':'🙈 Listen only to commands'
                                               if tg_lib.all_mode_check(db, msg['chat']['id'])
                                               else '🐵 Listen to all message'}])

        await sendKeyboard(msg['chat']['id'],
                            f"Mode was changed via @{msg['from']['username']} (ON)",
                            {'keyboard': tmp_settings_keyboard,
                             'resize_keyboard': True,
                             'selective':True })
    if command == 'all_mode_off':
        tg_lib.all_mode_off(db, msg['chat']['id'])
        tmp_settings_keyboard = deepcopy(SETTINGS_KEYBOARD)
        tmp_settings_keyboard.append([{'text':'🙈 Listen only to commands'
                                               if tg_lib.all_mode_check(db, msg['chat']['id'])
                                               else '🐵 Listen to all message'}])

        await sendKeyboard(msg['chat']['id'],
                            f"Mode was changed via @{msg['from']['username']} (OFF)",
                            {'keyboard': tmp_settings_keyboard,
                             'resize_keyboard': True,
                             'selective':True })


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
                print(f"[{time.ctime()}] Message: {msg['text']}")
                await seek_and_send(vk_audio, db, msg)
    else:
        pprint(msg)

async def workerCallback(vk_audio, db, callback):
    data = callback['data'].split('@')
    print(f"[{time.ctime()}] Callback data: {data}")
    command, data = data[0], data[1:]

    if command == 'd' :
        audio_id = data[0]+'_'+data[1]

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

            while True:
                try:
                    new_audio = await vk_audio.get_audio_by_id(*data)
                except ConnectionError:
                    asyncio.sleep(1)
                else:
                    break

            #download audio
            response = await requests.get(new_audio['url'])
            audio_size = int(response.headers.get('content-length', 0)) / MEGABYTE_SIZE
            #send new audio file
            response = await sendAudio(callback['message']['chat']['id'],
                                        file = response.content,
                                        title = new_audio['title'],
                                        performer = new_audio['artist'],
                                        caption='{:.2f} MB f\n_via MusicForUs\_bot_'.format(audio_size).replace('.','\.'),
                                        parse_mode='markdownv2')
            del new_audio

            #multiline comment
            '''
            response = await requests.head(new_audio['url'], allow_redirects=True)
            audio_size = int(response.headers.get('content-length', 0)) / MEGABYTE_SIZE
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
        current_page = int(data[0])
        request = data[1]

        while True:
            try:
                if request == "!popular":
                    res_generator = vk_audio.get_popular_iter(offset=(current_page-1)*MUSIC_LIST_LENGTH )
                elif request == "!new_songs":
                    res_generator = vk_audio.get_news_iter(offset=(current_page-1)*MUSIC_LIST_LENGTH )
                else:
                    res_generator = vk_audio.search_iter(request, offset=(current_page-1)*MUSIC_LIST_LENGTH )

                musiclist, NEXT_PAGE_FLAG = await tg_lib.get_music_list(res_generator, current_page, MUSIC_LIST_LENGTH)
            except ConnectionError:
                asyncio.sleep(1)
            else:
                break

        #construct inline keyboard for list
        inline_keyboard = tg_lib.get_inline_keyboard(musiclist, request, NEXT_PAGE_FLAG, current_page)

        #send answer
        await editKeyboard(callback['message']['chat']['id'], \
                            callback['message']['message_id'], \
                            {'inline_keyboard':inline_keyboard})

    if command == 'h':
        current_page = int(data[0])
        request = data[1]
        inline_keyboard = [[{
                             'text':'⤵️ Show',
                             'callback_data': f'e@{current_page}@{request}'
                            }]]
        await editKeyboard(callback['message']['chat']['id'], \
                            callback['message']['message_id'], \
                            {'inline_keyboard':inline_keyboard})

    if command == "pass":
        pass


#demons
async def result_demon(vk_audio, db, result):
    #just message
    if 'message' in result:
        await workerMsg(vk_audio, db, result['message'])
    #callback
    elif 'callback_query' in result:
        await workerCallback(vk_audio, db, result['callback_query'])
    elif 'edited_message' in result:
        pass
    #unknow update
    else:
        pprint(result)
    return



#listeners
#~~flask~~ vibora, requests
async def WHlistener(vk_audio, db):
    #asyncio.get_event_loop().set_debug(True)

    if SELF_SSL:
        #create ssl for webhook
        create_self_signed_cert(CERT_DIR)
        with open(os.path.join(CERT_DIR, CERT_FILE), "rb") as f:
            await setWebhook(WEBHOOK_URL, certificate = f)
    else:
        await setWebhook(WEBHOOK_URL)

    response = await getWebhookInfo()
    if response.json()['result']['url'] != WEBHOOK_URL:
        print(f"[{time.ctime()}] WebHook wasn't setted!")
        pprint(response.json())
        print(f"[{time.ctime()}] Shut down...")
        return


    app_listener = Sanic(__name__)

    @app_listener.route('/{}/'.format(TG_TOKEN), methods = ['GET','POST'])
    async def receive_update(request):
        if request.method == "POST":
            await result_demon(vk_audio, db, request.json)
        return sanic_json({"ok": True})

    print(f"[{time.ctime()}] Listening...")
    server = app_listener.create_server(host = HOST_IP, port = PORT, return_asyncio_server=True, access_log = False)
    asyncio.create_task(server)


#requests only
async def LPlistener(vk_audio, db):
    LONGPOLING_OFFSET = 0
    LONGPOLING_DELAY = 3

    #offwebhook
    await setWebhook()

    #start listen
    print(f"[{time.ctime()}] Listening...")
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

            async result_demon(vk_audio, db, result)

#start func
def start_bot(WEB_HOOK_FLAG = True):
    print(f"[{time.ctime()}] Start...")
    #print important constants
    print("""
            TG_TOKEN: {}
            VK_LOGIN: {}
            VK_PASSWORD: {}
            TG_URL: {}
            TG_SHELTER: {}
            WEB HOOK: {}
            WEBHOOK_DOMEN: {}
            WEBHOOK_URL: {}
            HOST_IP: {}
            PORT: {}""".format(TG_TOKEN,
            VK_LOGIN,
            VK_PASSWORD,
            TG_URL,
            TG_SHELTER,
            WEB_HOOK_FLAG,
            WEBHOOK_DOMEN,
            WEBHOOK_URL,
            HOST_IP,
            PORT))

    try:
        #database loading
        print(f"[{time.ctime()}] Database loading...")
        db_connect = sqlite3.connect("botbase.db")
        db_cursor = db_connect.cursor()

        db = namedtuple('Database', 'conn cursor')(conn = db_connect, cursor = db_cursor)
        #if new database
        try:
            #audios table
            db_cursor.execute(
                """CREATE TABLE audios
                (id TEXT PRIMARY KEY,
                telegram_id TEXT NOT NULL,
                audio_size FLOAT NOT NULL)""")
        except sqlite3.OperationalError:
            pass

        try:
            #all_mode table
            db_cursor.execute(
                """CREATE TABLE chat_modes
                (id TEXT PRIMARY KEY,
                mode BOOL NOT NULL)""")
        except sqlite3.OperationalError:
            pass

        loop = asyncio.get_event_loop()
        #autetifications in vk
        print(f"[{time.ctime()}] Vk autentification...")
        vk_session = AsyncVkApi(VK_LOGIN, VK_PASSWORD, auth_handler=tg_lib.auth_handler, loop = loop)
        vk_session.auth()

        #vk audio class for fetching music
        vk_audio = AsyncVkAudio(vk_session)

        #pick type of listener and run
        loop.create_task((WHlistener if WEB_HOOK_FLAG else LPlistener)(vk_audio, db))
        loop.run_forever()

    except (KeyboardInterrupt, ):
        #Force exit with ctrl+C
        loop.close()
        print(f"[{time.ctime()}] Key force exit.")
    except Exception as err:
        #Any error should send ping message to developer
        print(f"[{time.ctime()}] я упал :с")
        while True:
            print(f"[{time.ctime()}] Пробую уведомить о падении...")
            try:
                asyncio.run(sendMessage(TG_SHELTER, "я упал :с"))
            except Exception:
                time.sleep(60)
            else:
                break
        loop.close()
        raise(err)

if __name__ == "__main__":
    #parse args

    parser = argparse.ArgumentParser()
    parser.add_argument('-wh', action="store", dest="webhook_on", default=0, type=int)
    parser.add_argument('-p', action="store", dest="port", default=None, type=int)
    parser.add_argument('-i', action="store", dest="ip", default=None)
    parser.add_argument('-d', action="store", dest="domen", default=None)
    parser.add_argument('-s', action="store", dest="ssl", default=None, type=int)
    args = parser.parse_args()

    if args.port: PORT = args.port
    if args.ip: HOST_IP = args.ip
    if args.domen:
        WEBHOOK_DOMEN = args.domen
        WEBHOOK_URL = "https://"+ WEBHOOK_DOMEN +"/"+ TG_TOKEN +"/"
    if args.ssl != None:
        SELF_SSL = bool(args.ssl)
    #if main then start bot
    start_bot(bool(args.webhook_on))
