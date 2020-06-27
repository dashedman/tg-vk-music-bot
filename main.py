import asyncio
import sqlite3
import requests

import json
from pprint import pprint


TG_TOKEN = "852691034:AAHzAeHXe4iGnG1k3Mxkr3tXN9UaFd71gU0"
TG_URL = "https://api.telegram.org/bot"+ TG_TOKEN +"/"
TG_SHELTER = "@dashed_man"

HOOK_DOMEN = ""
HOOK_URL = "https://"+ HOOK_DOMEN +"/"+ TG_TOKEN +"/"

LONGPOLING_OFFSET = 0

OLD_UPDATES = set()

async def webHookGet():
    pass

async def longPoling():
    global LONGPOLING_OFFSET
    success = False

    while not success:
            r = requests.get(TG_URL + 'getUpdates',params =  {"offset":LONGPOLING_OFFSET} ).json()
            success = r['ok']
            await asyncio.sleep(5)

    for result in r['result']:
        LONGPOLING_OFFSET = max(LONGPOLING_OFFSET,result['update_id'])+1
    return r


async def sendMessage(chat_id,text=""):
    link = {
        'chat_id':chat_id,
        'text': text
    }
    r = requests.post(TG_URL + 'sendMessage', json = link).json()
    pprint(r)
    if not r['ok']:
        raise("no ok")

async def worker(msg):
    await sendMessage(msg['chat']['id'], json.dumps(msg))



async def listener(WEB_HOOK_FLAG = False):
    getUpdate = webHookGet if WEB_HOOK_FLAG else longPoling
    print("Listening...")
    while True:
        r = await getUpdate()

        for result in r['result']:
            asyncio.create_task(worker(result['message']))


def start_bot():
    print("Start...")
    asyncio.run(listener())


if __name__ == "__main__":
    try:
        start_bot()
    except KeyboardInterrupt:
        print("Key force exit.")
