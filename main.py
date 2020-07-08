import asyncio
import sqlite3
import time
import re
import argparse
import json
import sys
import os

from pprint import pprint
from collections import namedtuple
from copy import deepcopy
from functools import partial

#import requests
#asynchronious requests-like
import requests_async as requests

#vk_api...
from vk_api import VkApi
#from vk_api.audio import VkAudio
from audio import VkAudio

#asynchronious flask-like
from sanic import Sanic
from sanic.response import json as sanic_json

#my local lib
import tg_lib
from ui_constants import *

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

MEGABYTE_SIZE = 1<<20
MUSIC_LIST_LENGTH = 9
IS_DOWLOAD = set()


#functions

#tg send functions
async def setWebhook(url=''):
    await requests.post(TG_URL + 'setWebhook', json = {'url':url}, timeout=None)

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
    res_generator = vk_audio.search_iter(request)

    NEXT_PAGE_FLAG = False
    current_page = 1
    musiclist = []
    try:
        musiclist.append(next(res_generator))
    except StopIteration:
        pass
    else:
        for i in range(MUSIC_LIST_LENGTH-1):
            try:
                next_track = next(res_generator)
                if next_track == musiclist[0]:break
                musiclist.append( next_track )
            except StopIteration:
                break
        else:
            try:
                 next(res_generator)
                 NEXT_PAGE_FLAG = True
            except StopIteration:
                pass

    if not musiclist:
        await sendMessage(msg['chat']['id'],
                            'По вашему запросу ничего не нашлось :c',
                            msg['message_id'])
        return
    #construct inline keyboard for list
    inline_keyboard = []
    for music in musiclist:
        #print(music)
        duration = time.gmtime(music['duration'])
        inline_keyboard.append([tg_lib.callback_button( \
                                    f"{music['artist']} - {music['title']} ({duration.tm_min}:{duration.tm_sec:02})",
                                    f"d@{music['owner_id']}@{music['id']}"
                                )])


    inline_keyboard.append([
        tg_lib.callback_button( '⛔️', 'pass@'),
        tg_lib.callback_button( current_page, 'pass@'),

    ])
    if NEXT_PAGE_FLAG:
        inline_keyboard[-1].append(tg_lib.callback_button( '▶️', f'e@{current_page+1}@{request}'))
    else:
        inline_keyboard[-1].append(tg_lib.callback_button( '⛔️', 'pass@'))
    inline_keyboard[-1].append(tg_lib.callback_button( '⤴️ Hide', f'h@{current_page}@{request}'))


    #send answer
    await sendKeyboard(msg['chat']['id'], \
                        msg['text'], \
                        {'inline_keyboard':inline_keyboard}, \
                        msg['message_id'])

async def send_popular(vk_audio, db, msg):
    #seek music in vk
    res_generator = vk_audio.get_popular_iter()
    #get firsts 7
    musiclist = []
    for i in range(MUSIC_LIST_LENGTH):
        try:
            musiclist.append( next(res_generator) )
        except StopIteration:
            break
    #construct inline keyboard for list
    inline_keyboard = []
    for music in musiclist:
        #print(music)
        duration = time.gmtime(music['duration'])
        inline_keyboard.append([tg_lib.callback_button( \
                                    '{} - {} ({}:{:02})'.format(music['artist'], \
                                                             music['title'], \
                                                             duration.tm_min, \
                                                             duration.tm_sec), \
                                    '{}@{}@{}'.format('d', \
                                                      music['owner_id'], \
                                                      music['id'])
                                )])
    #send answer
    await sendKeyboard(msg['chat']['id'], \
                        msg['text'], \
                        {'inline_keyboard':inline_keyboard}, \
                        msg['message_id'])

async def send_new_songs(vk_audio, db, msg):
    #seek music in vk
    res_generator = vk_audio.get_news_iter()
    #get firsts 7
    musiclist = []
    for i in range(MUSIC_LIST_LENGTH):
        try:
            musiclist.append( next(res_generator) )
        except StopIteration:
            break
    #construct inline keyboard for list
    inline_keyboard = []
    for music in musiclist:
        #print(music)
        duration = time.gmtime(music['duration'])
        inline_keyboard.append([tg_lib.callback_button( \
                                    '{} - {} ({}:{:02})'.format(music['artist'], \
                                                             music['title'], \
                                                             duration.tm_min, \
                                                             duration.tm_sec), \
                                    '{}@{}@{}'.format('d', \
                                                      music['owner_id'], \
                                                      music['id'])
                                )])
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
                print('Message:', msg['text'])
                await seek_and_send(vk_audio, db, msg)
    else:
        pprint(msg)

async def workerCallback(vk_audio, db, callback):
    data = callback['data'].split('@')
    print('Callback data:', data)
    command, data = data[0], data[1:]

    if command == 'd' :
        audio_id = data[0]+'_'+data[1]

        while audio_id in IS_DOWLOAD:
            await asyncio.sleep(0.07)
        #check audio in old loads
        if audio_data := tg_lib.db_get_audio(db, audio_id):
            telegram_id, audio_size = audio_data
            #send id from old audio in telegram
            await sendAudio(callback['message']['chat']['id'], \
                            telegram_id = telegram_id,
                            caption='{:.2f} MB t\n_via MusicForUs\_bot_'.format(audio_size).replace('.','\.'),
                            parse_mode='markdownv2')

        else:
            IS_DOWLOAD.add(audio_id)
            new_audio = await asyncio.get_running_loop().run_in_executor(
                                                              None,
                                                              vk_audio.get_audio_by_id,
                                                              *data
                                                         )
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
            IS_DOWLOAD.discard(audio_id)

    if command == 'e':
        current_page = int(data[0])
        request = data[1]
        res_generator = vk_audio.search_iter(request, offset=(current_page-1)*MUSIC_LIST_LENGTH)

        NEXT_PAGE_FLAG = False
        musiclist = []
        try:
            musiclist.append(next(res_generator))
        except StopIteration:
            pass
        else:
            for i in range(MUSIC_LIST_LENGTH-1):
                try:
                    next_track = next(res_generator)
                    if next_track == musiclist[0]:break
                    musiclist.append( next_track )
                except StopIteration:
                    break
            else:
                try:
                     next(res_generator)
                     NEXT_PAGE_FLAG = True
                except StopIteration:
                    pass

        #construct inline keyboard for list
        inline_keyboard = []
        for music in musiclist:
            #print(music)
            duration = time.gmtime(music['duration'])
            inline_keyboard.append([tg_lib.callback_button( \
                                        f"{music['artist']} - {music['title']} ({duration.tm_min}:{duration.tm_sec:02})",
                                        f"d@{music['owner_id']}@{music['id']}"
                                    )])

        inline_keyboard.append([])
        if current_page > 1:
            inline_keyboard[-1].append(tg_lib.callback_button( '◀️', f'e@{current_page-1}@{request}'))
        else:
            inline_keyboard[-1].append(tg_lib.callback_button( '⛔️', 'pass@'))

        inline_keyboard[-1].append(tg_lib.callback_button( current_page, 'pass@'))

        if NEXT_PAGE_FLAG:
            inline_keyboard[-1].append(tg_lib.callback_button( '▶️', f'e@{current_page+1}@{request}'))
        else:
            inline_keyboard[-1].append(tg_lib.callback_button( '⛔️', 'pass@'))
        inline_keyboard[-1].append(tg_lib.callback_button( '⤴️ Hide', f'h@{current_page}@{request}'))

        #send answer
        await editKeyboard(callback['message']['chat']['id'], \
                            callback['message']['message_id'], \
                            {'inline_keyboard':inline_keyboard})

    if command == 'h':
        current_page = int(data[0])
        request = data[1]
        inline_keyboard = [[tg_lib.callback_button( '⤵️ Show', f'e@{current_page}@{request}')]]
        await editKeyboard(callback['message']['chat']['id'], \
                            callback['message']['message_id'], \
                            {'inline_keyboard':inline_keyboard})

    if command == "pass":
        pass


#demon for tg update
def result_demon(vk_audio, db, result):
    #just message
    if 'message' in result:
        asyncio.create_task( workerMsg(vk_audio, db, result['message']) )
    #callback
    elif 'callback_query' in result:
        asyncio.create_task( workerCallback(vk_audio, db, result['callback_query']) )
    elif 'edited_message' in result:
        pass
    #unknow update
    else:
        pprint(result)
    return

async def vk_ping_demon(vk_audio):
    while True:
        try:
            vk_audio._vk.http.head("https://vk.com/al_audio.php")
        except Exception as e:
            print(f"Error: {e}")
            continue
        await asyncio.sleep(270)
#listeners
#~~flask~~ vibora, requests
async def WHlistener(vk_audio, db):

    app_listener = Sanic(__name__)

    @app_listener.route('/{}/'.format(TG_TOKEN), methods = ['GET','POST'])
    async def receive_update(request):
        if request.method == "POST":
            result_demon(vk_audio, db, request.json)
        return sanic_json({"ok": True})

    await setWebhook(WEBHOOK_URL)
    response = await getWebhookInfo()
    if response.json()['result']['url'] != WEBHOOK_URL:
        print(f"[{time.ctime()}] WebHook wasn't setted!")
        pprint(response.json())
        print(f"[{time.ctime()}] Shut down...")
        return

    print(f"[{time.ctime()}] Listening...")
    server = app_listener.create_server(host = HOST_IP, port = PORT, return_asyncio_server=True)
    asyncio.create_task(server)
    await vk_ping_demon(vk_audio)



#requests only
async def LPlistener(vk_audio, db):
    LONGPOLING_OFFSET = 0
    LONGPOLING_DELAY = 3

    asyncio.create_task(vk_ping_demon(vk_audio))

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
            result_demon(vk_audio, db, result)

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
        db_connect = sqlite3.connect(".gitignore/botbase.db")
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

        #autetifications in vk
        print(f"[{time.ctime()}] Vk autentification...")
        vk_session = VkApi(VK_LOGIN, VK_PASSWORD, auth_handler=tg_lib.auth_handler)
        vk_session.auth()
        #vk audio class for fetching music
        vk_audio = VkAudio(vk_session)

        '''gen = vk_audio.search_iter("молли",offset = 106)
        for i in range(210):#
            next(gen)
        return #'''

        #pick type of listener
        if WEB_HOOK_FLAG:
            #run sanic server
            asyncio.run(WHlistener(vk_audio, db))
        else:
            #run asyncronious listener
            asyncio.run(LPlistener(vk_audio, db))
    except (KeyboardInterrupt, ):
        #Force exit with ctrl+C
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
        raise(err)

if __name__ == "__main__":

    #parse args
    parser = argparse.ArgumentParser()
    parser.add_argument('-wh', action="store", dest="webhook_on", default=0, type=int)
    parser.add_argument('-p', action="store", dest="port", default=None, type=int)
    parser.add_argument('-i', action="store", dest="ip", default=None)
    parser.add_argument('-d', action="store", dest="domen", default=None)
    args = parser.parse_args()

    if args.port: PORT = args.port
    if args.ip: HOST_IP = args.ip
    if args.domen:
        WEBHOOK_DOMEN = args.domen
        WEBHOOK_URL = "https://"+ WEBHOOK_DOMEN +"/"+ TG_TOKEN +"/"
    #if main then start bot
    start_bot(bool(args.webhook_on))
