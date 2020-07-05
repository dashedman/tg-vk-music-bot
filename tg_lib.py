
from vk_api.audio import VkAudio, scrap_data

#my class that extend audio vk api class for popular and new music
class VkAudioExtended(VkAudio):
    def get_popular_iter(self,offset=0):
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

        tracks = scrap_data(
            response.text,
            self.user_id,
            convert_m3u8_links=self.convert_m3u8_links,
            http=self._vk.http
        )

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

        tracks = scrap_data(
            response.text,
            self.user_id,
            convert_m3u8_links=self.convert_m3u8_links,
            http=self._vk.http
        )

        for track in tracks:
            yield track

    def get_audio_by_id(self, owner_id, audio_id):
        """ Получить аудиозапись по ID
        :param owner_id: ID владельца (отрицательные значения для групп)
        :param audio_id: ID аудио
        """
        response = self._vk.http.get(
            'https://m.vk.com/audio{}_{}'.format(owner_id,audio_id),
            allow_redirects=False
        )
        track = scrap_data(
            response.text,
            self.user_id,
            filter_root_el={'class': 'basisDefault'},
            convert_m3u8_links=self.convert_m3u8_links,
            http=self._vk.http
        )
        if track:
            return track[0]
        else:
            return ''


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
    return bool(db.cursor.fetchone()[0])

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
