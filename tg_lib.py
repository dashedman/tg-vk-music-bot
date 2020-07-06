

def auth_handler():
    return input("Key code:"), False

def callback_button(text = '', callback_data = ''):
    return {
        'text':text,
        'callback_data':callback_data
    }


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
