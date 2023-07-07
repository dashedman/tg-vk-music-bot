import time
import html
import aiogram.utils.markdown as md
from aiogram.types.reply_keyboard import ReplyKeyboardMarkup, KeyboardButton as RKB
from aiogram.types.inline_keyboard import InlineKeyboardMarkup, InlineKeyboardButton as IKB

unescape = lambda s: html.unescape(s.replace("$#","&#"))

SIGNATURE = ""
def set_signature(bot_name: str):
    global SIGNATURE
    SIGNATURE = md.hitalic("via "+bot_name)

YES = "🟢"
NO = "🔴"
BACK = "⬆️ Back"
HIDE = "⤴️ Hide"
SHOW = "⤵️ Show"
PREV = "◀️"
NEXT = "▶️"
STOP = "⛔️"
REFRESH = "🔄"
ROCKET = "🚀"

NO_CONFIG_MESSAGE = "Please take config.ini from developers"
SETTINGS = "Settings.."
MODE_ON = "Mode was changed (ON)"
MODE_OFF = "Mode was changed (OFF)"

ADDED = "Succsesfully added!"
SETTED = "Succsesfully setted!"
DELETED = "Succsesfully deleted!"
SENDED = "Succsesfully sent!"
FINDED = "По вашему запросу нашлось"

WAIT = "Please wait..."
WRONG = "Wrong command("
ERROR = "Что-то сломалось :c"
NOT_FOUND = "По вашему запросу ничего не нашлось :с"
NOTHING_NEW = "Nothing is new."
FIND_NO_ARGS = "Please write '/find some text' to seek streams.\nMinimal length of text 3!\nMaximal length of text 30!"
TOO_SMALL = "Message is to small"
TOO_BIG = "Слишком большой запрос :с"
EMPTY = "Ваш запрос пуст. Поcмотрите примеры в /help"
UNKNOW_CMD = "Unknow command =/\nEnter /help to get list of commands"
NO_ACCESS = "Недостаточно прав!"
OLD_MESSAGE = "Sorry. It's message is out of date :("


MAIN_KEYBOARD = ReplyKeyboardMarkup(keyboard=[
    [RKB(text='👑 Popular'), RKB(text='🆕 New songs')],
    [RKB(text='❓ Help'),     RKB(text='📈 Bot State')],
    [RKB(text='🔨 Settings'),    RKB(text='📔 About')]
], resize_keyboard=True, one_time_keyboard=True, selective=True)

SETTINGS_KEYBOARD = [
    [RKB(text='↩️ Back')]
]

KEYBOARD_COMMANDS = { 'popular':'👑 Popular',
                      'new_songs':'🆕 New songs',
                      'help':'❓ Help',
                      'settings':'🔨 Settings',
                      'about':'📔 About',
                      'get_state':'📈 Bot State',
                      'all_mode_on':'🐵 Listen to all message',
                      'all_mode_off':'🙈 Listen only to commands',
                      'start':'↩️ Back'}


HELP_TEXT = """❓ Help
/start - получить основную клавиатуру.

/help - рекурсия...
/about - информация о разработчике.
/get_state - состояние бота.

/find - искать музыку🔍. Чтобы воспользоватся после команды надо написать название или автора произведения.
Синоним: /f
Пример: "/find zoom - last dinosaurs"
Пример: "/f zoom - last dinosaurs"

/popular - получить список самых популярных треков.
Синоним: /chart

/new_songs - получить список новинок.
Синоним: /novelties

/review - написать разработчику
Синоним: /r
Пример: "/review Привет!"
Пример: "/r Привет!"


Для админов чатов:
/settings - открыть настройки.
/all_mode_on - включить публичный мод.
/all_mode_off - отключить публичный мод.

Публичный мод - мод в котором бот читает все сообщения и воспринимает их как запрос к поиску /find.
Если мод отключен, бот реагирует только на команды.
"""

VIPHELP_TEXT = """
/vipinfo - get raw info about msg
/viphelp - get help for admin commands

/log - get last log
/logs - get all logs

/set_state - set new bot state. "/set_state text"
/cache - get online cache in bot

/err - raise err in bot
"""

ABOUT_TEXT = """📔 About!
📫 For any questions: @dashed_man
py3.8"""


def get_inline_keyboard(musiclist, request, NEXT_PAGE_FLAG, current_page=1):
    inline_keyboard = []
    for music in musiclist:
        duration = time.gmtime(music['duration'])
        inline_keyboard.append([
            IKB(
                text=html.unescape(f"{music['artist']} - {music['title']} ({duration.tm_min}:{duration.tm_sec:02})".replace("$#", "&#")),
                callback_data=f"d@{music['owner_id']}@{music['id']}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def get_hide_keyboard(request, current_page):
    return InlineKeyboardMarkup(inline_keyboard=[[IKB(
        text=SHOW,
        callback_data= f'e@{request}@{current_page}'
    )]])


def starting_download(title: str, artist: str):
    return f'{ROCKET} {title} - {artist}'


def build_review_info(message):
    return f"Review from {md.quote_html(message.from_user.mention)}(user: {md.hcode(message.from_user.id)}, chat: {md.hcode(message.chat.id)}){'[is a bot]' if message.from_user.is_bot else ''}"
