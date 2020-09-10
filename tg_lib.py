import time
import html
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

def get_inline_keyboard(musiclist, request, NEXT_PAGE_FLAG, current_page=1):
    inline_keyboard = []
    for music in musiclist:
        duration = time.gmtime(music['duration'])
        inline_keyboard.append([{
                                    'text': html.unescape(f"{music['artist']} - {music['title']} ({duration.tm_min}:{duration.tm_sec:02})".replace("$#","&#")),
                                    'callback_data':f"d@{music['owner_id']}@{music['id']}"
                                }])

    inline_keyboard.append([])
    if current_page > 1:
        inline_keyboard[-1].append({
                                    'text': '◀️',
                                    'callback_data': f'e@{request}@{current_page-1}'
                                   })
    else:
        inline_keyboard[-1].append({
                                    'text': '⛔️',
                                    'callback_data': 'pass@'
                                   })

    inline_keyboard[-1].append({
                                'text': current_page,
                                'callback_data': 'pass@'
                               })

    if NEXT_PAGE_FLAG:
        inline_keyboard[-1].append({
                                    'text': '▶️',
                                    'callback_data': f'e@{request}@{current_page+1}'
                                   })
    else:
        inline_keyboard[-1].append({
                                    'text': '⛔️',
                                    'callback_data': 'pass@'
                                   })
    inline_keyboard[-1].append({
                                'text': '⤴️ Hide',
                                'callback_data': f'h@{request}@{current_page}'
                               })
    return inline_keyboard

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
                if next_track == musiclist[0]:break
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

async def get_ad_generator(vk_audio, db, ad_id):

    ad_json_list = get_ad(db, ad_id)
    if ad_json_list:
        ad_track_list = json.loads(ad_json_list[2])
        for track in ad_track_list:
            yield track

def get_ad(db, ad_id=None):
    if ad_id:
        db.cursor.execute(
            """SELECT id, caption, track_list, counter FROM ad_buffer
            WHERE id=?"""
            , (ad_id, ))
    else:
        db.cursor.execute(
            """SELECT id, caption, track_list, counter FROM ad_buffer
            ORDER BY RANDOM() LIMIT 1""")
    return db.cursor.fetchone()

def put_ad(db, ad_id, caption, track_list, counter=0):
    if ad_id:
        try:
            db.cursor.execute(
                """UPDATE ad_buffer
                SET caption=?, track_list=?, counter=?
                WHERE id=?"""
                ,(caption, track_list, counter, ad_id))
        except sqlite3.IntegrityError:
            db.cursor.execute(
                """INSERT INTO ad_buffer
                VALUES (?,?,?,?)"""
                , (ad_id, caption, track_list, counter))
    else:
        db.cursor.execute(
            """INSERT INTO ad_buffer (caption, track_list, counter)
            VALUES (?,?,?)"""
            , ( caption, track_list, counter))
    db.conn.commit()

def increment_ad(db, ad_id, increment = None):
    if increment:
        db.cursor.execute(
            """UPDATE ad_buffer
            SET counter=?
            WHERE id=?"""
            ,(increment, ad_id))
    else:
        db.cursor.execute(
            """SELECT counter FROM ad_buffer
            WHERE id=?"""
            , (ad_id, ))
        increment = db.cursor.fetchone()[0] + 1
        db.cursor.execute(
            """UPDATE ad_buffer
            SET counter=?
            WHERE id=?"""
            ,(increment, ad_id))

def decrement_ad(db, ad_id, decrement = None):
    if decrement:
        db.cursor.execute(
            """UPDATE ad_buffer
            SET counter=?
            WHERE id=?"""
            ,(decrement, ad_id))
    else:
        db.cursor.execute(
            """SELECT counter FROM ad_buffer
            WHERE id=?"""
            , (ad_id, ))
        decrement = db.cursor.fetchone()[0] - 1
        db.cursor.execute(
            """UPDATE ad_buffer
            SET counter=?
            WHERE id=?"""
            ,(decrement, ad_id))

def delete_ad(db, ad_id):
    db.cursor.execute(
        """DELETE FROM ad_buffer WHERE id=?"""
        ,(ad_id, ))
    db.conn.commit()


def db_get_audio(db, audio_id):
    db.cursor.execute(
        """SELECT telegram_id, audio_size FROM audios
        WHERE id=?"""
        , (audio_id, ))
    return db.cursor.fetchone()

def db_put_audio(db, audio_id, telegram_id, audio_size):
    try:
        db.cursor.execute(
            """INSERT INTO audios
            VALUES (?,?,?)"""
        , (audio_id, telegram_id, audio_size))
    except sqlite3.IntegrityError:
        pass
    db.conn.commit()

def db_del_audio(db, audio_id):
    db.cursor.execute(
        """DELETE FROM audios WHERE id=?"""
        ,(audio_id, ))
    db.conn.commit()

def all_mode_check(db, chat_id):
    db.cursor.execute(
        """SELECT mode FROM chats
        WHERE id=?"""
        , (chat_id, ))
    answer = db.cursor.fetchone()
    if answer == None:
        db.cursor.execute(
            """INSERT INTO chats
            VALUES (?,?,?)"""
            , (chat_id, False, 25))
        answer = [False]
    return bool(answer[0])

def all_mode_on(db, chat_id):
    try:
        db.cursor.execute(
            """UPDATE chats
            SET mode=?
            WHERE id=?"""
            , (True, chat_id))
    except sqlite3.IntegrityError:
        db.cursor.execute(
            """INSERT INTO chats
            VALUES (?,?)"""
            , (chat_id, True))
    db.conn.commit()

def all_mode_off(db, chat_id):
    try:
        db.cursor.execute(
            """UPDATE chats
            SET mode=?
            WHERE id=?"""
            , (False, chat_id))
    except sqlite3.IntegrityError:
        db.cursor.execute(
            """INSERT INTO chats
            VALUES (?,?)"""
            , (chat_id, False))
    db.conn.commit()

def get_chat_counter(db, chat_id):
    db.cursor.execute(
        """SELECT ad_counter FROM chats
        WHERE id=?"""
        , (chat_id, ))
    answer = db.cursor.fetchone()
    if answer == None:
        db.cursor.execute(
            """INSERT INTO chats
            VALUES (?,?,?)"""
            , (chat_id, False, 25))
        answer = [25]
    return answer[0]

def put_chat_counter(db, chat_id, count = 25):
    try:
        db.cursor.execute(
            """UPDATE chats
            SET ad_counter=?
            WHERE id=?"""
            , (count, chat_id))
    except sqlite3.IntegrityError:
        db.cursor.execute(
            """INSERT INTO chats (id, ad_counter)
            VALUES (?,?)"""
            , (chat_id, count))
    db.conn.commit()
