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
        # musiclist.append( await generator.__anext__() )
        musiclist.append(next(generator))
    except StopIteration:
        pass
    else:
        for i in range(list_length-1):
            try:
                next_track = next(generator)
                if next_track['id'] == musiclist[0]['id'] and next_track['owner_id'] == musiclist[0]['owner_id']:
                    break
                musiclist.append(next_track)
            except StopIteration:
                break


        else:
            try:
                 next(generator)
                 NEXT_PAGE_FLAG = True
            except StopIteration:
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
            , (audio_id, ))


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
                VALUES (?,?)"""
                , (chat_id, False))
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
