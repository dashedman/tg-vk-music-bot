import time
import sqlite3
import json
import asyncio

class DictionaryBomb():
    def __init__(self, dict, key, timer=0):
        self.timer = timer
        self.dict = dict
        self.key = key
    def replant(self, timer):
        self.timer = timer
    async def plant(self):
        while self.timer >= time.time():
            await asyncio.sleep(0)
        self.dict.pop(self.key, None)


def auth_handler():
    return input("Key code:"), False



async def get_music_list(generator, current_page=1, list_length = 1):
    NEXT_PAGE_FLAG = False
    musiclist = []
    try:
        musiclist.append( await generator.__anext__() )
    except StopAsyncIteration:
        pass
    else:
        for i in range(list_length-1):
            try:
                next_track = await generator.__anext__()
                if next_track['ID'] == musiclist[0]['ID'] and next_track['OWNER_ID'] == musiclist[0]['OWNER_ID']:break
                musiclist.append(next_track)
            except StopAsyncIteration:
                break


        else:
            try:
                 await generator.__anext__()
                 NEXT_PAGE_FLAG = True
            except StopAsyncIteration:
                pass

    return musiclist, NEXT_PAGE_FLAG

def db_get_audio(db, audio_id):
    with db:
        cur = db.cursor()
        cur.execute(
            """SELECT telegram_id, audio_size FROM audios
            WHERE id=?"""
            , (audio_id, ))
        return cur.fetchone()

def db_put_audio(db, audio_id, telegram_id, audio_size):
    try:
        with db:
            db.cursor().execute(
                """INSERT INTO audios
                VALUES (?,?,?)"""
            , (audio_id, telegram_id, audio_size))
    except sqlite3.IntegrityError:
        pass

def db_del_audio(db, audio_id):
    with db:
        db.cursor().execute(
            """DELETE FROM audios WHERE id=?"""
            ,(audio_id, ))

def all_mode_check(db, chat_id):
    with db:
        cur = db.cursor()
        cur.execute(
            """SELECT mode FROM chats
            WHERE id=?"""
            , (chat_id, ))
        answer = cur.fetchone()
        if answer == None:
            cur.execute(
                """INSERT INTO chats
                VALUES (?,?,?)"""
                , (chat_id, False, 25))
            answer = (False,)
    return bool(answer[0])

def all_mode_on(db, chat_id):
    with db:
        try:
            db.cursor().execute(
                """UPDATE chats
                SET mode=?
                WHERE id=?"""
                , (True, chat_id))
        except sqlite3.IntegrityError:
            db.cursor().execute(
                """INSERT INTO chats
                VALUES (?,?)"""
                , (chat_id, True))

def all_mode_off(db, chat_id):
    with db:
        try:
            db.cursor().execute(
                """UPDATE chats
                SET mode=?
                WHERE id=?"""
                , (False, chat_id))
        except sqlite3.IntegrityError:
            db.cursor().execute(
                """INSERT INTO chats
                VALUES (?,?)"""
                , (chat_id, False))
