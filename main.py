import asyncio
import sqlite3
import time
#import re
import json
import sys
import os

from pprint import pprint
from collections import namedtuple

#import requests
#asynchronious requests-like
import requests_async as requests

#vk_api...
from vk_api import VkApi
from vk_api.audio import VkAudio

#asynchronious flask-like
from sanic import Sanic
from sanic.response import json as sanic_json

#my local lib
import tg_lib
from tg_lib import VkAudioExtended

#constants
with open("botdata.ini","r") as f:
    TG_TOKEN = f.readline()[:-1]
    WEBHOOK_DOMEN = f.readline()[:-1]
    VK_LOGIN = f.readline()[:-1]
    VK_PASSWORD = f.readline()[:-1]

TG_URL = "https://api.telegram.org/bot"+ TG_TOKEN +"/"
TG_SHELTER = -479340226
WEBHOOK_URL = "https://"+ WEBHOOK_DOMEN +"/"+ TG_TOKEN +"/"

MEGABYTE_SIZE = 1<<20
MUSIC_LIST_LENGTH = 7

#functions

#tg send functions
async def setWebhook(url=''):
    await requests.post(TG_URL + 'setWebhook', json = {'url':url}, timeout=None)

async def sendMessage(chat_id,text=""):
    data = {
        'chat_id':chat_id,
        'text': text
    }

    response = await requests.post(TG_URL + 'sendMessage', json = data, timeout=None)
    r = response.json()

    if not r['ok']:
        pprint(r)
        raise("no ok")
    return r['result']

async def sendKeyboard(chat_id, text, keyboard, replay_message_id):
    data = {
        'chat_id':chat_id,
        'text': text,
        'reply_to_message_id': replay_message_id,
        'reply_markup': keyboard
    }

    response = await requests.post(TG_URL + 'sendMessage', json = data, timeout=None)
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


#asynchronious worker for proceed incoming messages
async def workerMsg(vk_audio, db, msg):
    print('Message:',msg['text'])
    #seek music in vk
    res_generator = vk_audio.search_iter(msg['text'])

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

#asynchronious worker for proceed incoming callbacks
async def workerCallback(vk_audio, db, callback):
    data = callback['data'].split('@')
    print('Callback data:', data)
    command, data = data[0], data[1:]

    if command == 'd' :
        audio_id = data[0]+'_'+data[1]
        #check audio in old loads
        audio_data = tg_lib.db_get_audio(db, audio_id)
        if audio_data:
            telegram_id, audio_size = audio_data
            #send id from old audio in telegram
            await sendAudio(callback['message']['chat']['id'], \
                            telegram_id = telegram_id,
                            caption='{:.2f} MB t\n_via MusicForUs\_bot_'.format(audio_size).replace('.','\.'),
                            parse_mode='markdownv2')

        else:
            new_audio = vk_audio.get_audio_by_id(*data)
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

#demon for tg update
def result_demon(vk_audio, db, result):
    #just message
    if 'message' in result:
        asyncio.create_task( workerMsg(vk_audio, db, result['message']) )
    #callback
    elif 'callback_query' in result:
        asyncio.create_task( workerCallback(vk_audio, db, result['callback_query']) )
    #unknow update
    else:
        pprint(result)


#web hook listener
#~~flask~~ vibora, requests
def WHlistener(vk_audio, db):

    app_listener = Sanic(__name__)

    @app_listener.route('/{}/'.format(TG_TOKEN), methods = ['GET','POST'])
    async def receive_update(request):
        if request.method == "POST":
            result_demon(vk_audio, db, request.json)
        return sanic_json({"ok": True})

    asyncio.run(setWebhook(WEBHOOK_URL))

    print("Listening...")
    app_listener.run(port = 88)

#long poling listener
#requests only
async def LPlistener(vk_audio, db):
    LONGPOLING_OFFSET = 0
    LONGPOLING_DELAY = 3

    #offwebhook
    await setWebhook()

    #start listen
    print("Listening...")
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


def start_bot(WEB_HOOK_FLAG = True):
    print("Start...")
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
            MUSIC_LIST_LENGTH: {}""".format(TG_TOKEN,
            VK_LOGIN,
            VK_PASSWORD,
            TG_URL,
            TG_SHELTER,
            WEB_HOOK_FLAG,
            WEBHOOK_DOMEN,
            WEBHOOK_URL,
            MUSIC_LIST_LENGTH))

    try:
        #database loading
        print("Database loading...")
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

        #autetifications in vk
        print("Vk autentification...")
        vk_session = VkApi(VK_LOGIN, VK_PASSWORD, auth_handler=tg_lib.auth_handler)
        vk_session.auth()
        #vk audio class for fetching music
        vk_audio = VkAudioExtended(vk_session)
        '''for i,a in enumerate(vk_audio.get_iter(192571881)):#earch_iter("Sex appeal")):#
            print(i,a)
            break
        return'''
        #pick type of listener
        if WEB_HOOK_FLAG:
            #run sanic server
            WHlistener(vk_audio, db)
        else:
            #run asyncronious listener
            asyncio.run(LPlistener(vk_audio, db))
    except KeyboardInterrupt:
        #Force exit with ctrl+C
        print("Key force exit.")
    except Exception as err:
        #Any error should send ping message to developer
        print("я упал :с")
        while True:
            print("Пробую уведомить о падении...")
            try:
                asyncio.run(sendMessage(TG_SHELTER, "я упал :с"))
            except Exception:
                time.sleep(10)
            else:
                break
        raise(err)

if __name__ == "__main__":
    #if main then start bot
    start_bot()
