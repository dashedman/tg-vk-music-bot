import asyncio
import sqlite3
import requests
import time
import re
import json

from vk_api import VkApi
from vk_api.audio import VkAudio, scrap_data
from pprint import pprint

#my local telegramm lib
import tg_lib

#my class that extend audio vk api class for popular and new music
class VkAudioExtended(VkAudio):
    def get_chart_iter(self,offset=0):
        """ Искать популярные аудиозаписи  (генератор)

        :param offset: смещение
        """

        response = self._vk.http.get(
            'https://m.vk.com/audio',
            params={
                'act':'popular',
                'offset':offset
            }
        )

        tracks = scrap_data(response.text, self.user_id)

        for track in tracks:
            yield track

    def get_new_iter(self):
        """ Искать новые аудиозаписи  (генератор)

        :param offset: смещение
        """

        response = self._vk.http.get(
            'https://m.vk.com/audio',
            params={
                'act':'popular'
            }
        )

        tracks = scrap_data(response.text, self.user_id)

        for track in tracks:
            yield track


#constants
with open("botdata.ini","r") as f:
    TG_TOKEN = f.readline()[:-1]
    VK_LOGIN = f.readline()[:-1]
    VK_PASSWORD = f.readline()[:-1]

TG_URL = "https://api.telegram.org/bot"+ TG_TOKEN +"/"
TG_SHELTER = -479340226

HOOK_DOMEN = ""
HOOK_URL = "https://"+ HOOK_DOMEN +"/"+ TG_TOKEN +"/"

LONGPOLING_OFFSET = 0
MUSIC_LIST_LENGTH = 7

#functions
async def sendMessage(chat_id,text=""):
    data = {
        'chat_id':chat_id,
        'text': text
    }
    r = requests.post(TG_URL + 'sendMessage', json = data).json()

    if not r['ok']:
        pprint(r)
        raise("no ok")

async def sendKeyboard(chat_id, text, keyboard, replay_message_id):
    data = {
        'chat_id':chat_id,
        'text': text,
        'reply_to_message_id': replay_message_id,
        'reply_markup': keyboard
    }
    r = requests.post(TG_URL + 'sendMessage', json = data).json()

    if not r['ok']:
        pprint(r)
        raise("no ok")

#web hook realisation
async def webHookGet():
    pass

#longpoling realisation
async def longPoling():
    global LONGPOLING_OFFSET
    success = False

    while not success:
        try:
            r = requests.get(TG_URL + 'getUpdates',params =  {"offset":LONGPOLING_OFFSET} ).json()
        except TimeoutError:
            pass
        else:
            success = r['ok']
        await asyncio.sleep(5)

    for result in r['result']:
        LONGPOLING_OFFSET = max(LONGPOLING_OFFSET,result['update_id'])+1
    return r


#listener for listen incoming messages
async def listener(vk_audio, WEB_HOOK_FLAG = False):

    #asynchronious worker for proceed incoming messages
    async def workerMsg(msg):

        #seek music in vk
        res_generator = vk_audio.search_iter(msg['text'])

        #get firsts 7
        musiclist = [next(res_generator) for i in range(MUSIC_LIST_LENGTH)]

        #construct inline keyboard for list
        inline_keyboard = []
        for music in musiclist:
            inline_keyboard.append([tg_lib.callback_button( \
                                        music['artist'] +' - '+ music['title'], \
                                        'download '+ str(music['id'])
                                    )])
        #send answer
        await sendKeyboard(msg['chat']['id'], \
                            msg['text'], \
                            {'inline_keyboard':inline_keyboard}, \
                            msg['message_id'])

    #asynchronious worker for proceed incoming messages
    async def workerCallback(msg):

        #seek music in vk
        res_generator = vk_audio.search_iter(msg['text'])

        #get firsts 7
        musiclist = [next(res_generator) for i in range(MUSIC_LIST_LENGTH)]

        #construct inline keyboard for list
        inline_keyboard = []
        for music in musiclist:
            print(music)
            inline_keyboard.append([tg_lib.callback_button( \
                                        music['artist'] +' - '+ music['title'], \
                                        'download '+ str(music['id'])
                                    )])
        #send answer
        await sendKeyboard(msg['chat']['id'], \
                            msg['text'], \
                            {'inline_keyboard':inline_keyboard}, \
                            msg['message_id'])


    #pick type of listening
    getUpdate = webHookGet if WEB_HOOK_FLAG else longPoling

    #start listen
    print("Listening...")
    while True:

        #get new messages
        r = await getUpdate()

        #go to proceed all of them
        for result in r['result']:
            if 'message' in result:
                asyncio.create_task( workerMsg(result['message']) )

            else if 'callback_query' in result:
                asyncio.create_task( workerCallback(result['callback_query']) )

            else:
                pprint(result)


def start_bot():
    print("Start...")
    #print important constants
    print("""
            TG_TOKEN: {}
            VK_LOGIN: {}
            VK_PASSWORD: {}
            TG_URL: {}
            TG_SHELTER: {}
            HOOK_DOMEN: {}
            HOOK_URL: {}
            MUSIC_LIST_LENGTH: {}""".format(TG_TOKEN,
            VK_LOGIN,
            VK_PASSWORD,
            TG_URL,
            TG_SHELTER,
            HOOK_DOMEN,
            HOOK_URL,
            MUSIC_LIST_LENGTH))

    try:
        #autetifications in vk
        print("Vk autentification...")
        vk_session = VkApi(VK_LOGIN, VK_PASSWORD)
        vk_session.auth()
        #vk audio class for fetching music
        vk_audio = VkAudioExtended(vk_session)

        #run asyncronious listener for incoming messages
        asyncio.run(listener(vk_audio))
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
    #if main start bot
    start_bot()
