import time
import html


def auth_handler():
    return input("Key code:"), False

def get_inline_keyboard(musiclist, request, NEXT_PAGE_FLAG, current_page=1):
    inline_keyboard = []
    for music in musiclist:
        #print(music)
        duration = time.gmtime(music['duration'])
        inline_keyboard.append([{
                                    'text': html.unescape(f"{music['artist']} - {music['title']} ({duration.tm_min}:{duration.tm_sec:02})".replace("$#","&#")),
                                    'callback_data':f"d@{music['owner_id']}@{music['id']}"
                                }])

    inline_keyboard.append([])
    if current_page > 1:
        inline_keyboard[-1].append({
                                    'text': '◀️',
                                    'callback_data': f'e@{current_page-1}@{request}'
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
                                    'callback_data': f'e@{current_page+1}@{request}'
                                   })
    else:
        inline_keyboard[-1].append({
                                    'text': '⛔️',
                                    'callback_data': 'pass@'
                                   })
    inline_keyboard[-1].append({
                                'text': '⤴️ Hide',
                                'callback_data': f'h@{current_page}@{request}'
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

def db_get_audio(db, audio_id):
    db.cursor.execute(
        """SELECT telegram_id, audio_size FROM audios
        WHERE id=?"""
        , (audio_id, ))
    return db.cursor.fetchone()

def db_put_audio(db, audio_id, telegram_id, audio_size):
    db.cursor.execute(
        """INSERT INTO audios
        VALUES (?,?,?)"""
        , (audio_id, telegram_id, audio_size))
    db.conn.commit()

def all_mode_check(db, chat_id):
    db.cursor.execute(
        """SELECT mode FROM chat_modes
        WHERE id=?"""
        , (chat_id, ))
    answer = db.cursor.fetchone()
    if answer == None:
        db.cursor.execute(
            """INSERT INTO chat_modes
            VALUES (?,?)"""
            , (chat_id, False))
        answer = [False]
    return bool(answer[0])

def all_mode_on(db, chat_id):
    try:
        db.cursor.execute(
            """UPDATE chat_modes
            SET mode=?
            WHERE id=?"""
            , (True, chat_id))
    except sqlite3.IntegrityError:
        db.cursor.execute(
            """INSERT INTO chat_modes
            VALUES (?,?)"""
            , (chat_id, True))
    db.conn.commit()

def all_mode_off(db, chat_id):
    try:
        db.cursor.execute(
            """UPDATE chat_modes
            SET mode=?
            WHERE id=?"""
            , (False, chat_id))
    except sqlite3.IntegrityError:
        db.cursor.execute(
            """INSERT INTO chat_modes
            VALUES (?,?)"""
            , (chat_id, False))
    db.conn.commit()
