MAIN_KEYBOARD = [[{'text':'👑 Popular'},{'text':'🆕 New songs'}],
                 [{'text':'❓ Help'},{'text':'🔨 Settings'},{'text':'📔 About'},{'text':'📈 Statistic'}]]

SETTINGS_KEYBOARD = [[{'text':'↩️ Back'},{'text':'⌨️ Review Keyboar'}]]

KEYBOARD_COMMANDS = { '👑 Popular':'popular',
                      '🆕 New songs':'new_songs',
                      '❓ Help':'help',
                      '🔨 Settings':'settings',
                      '📔 About':'about',
                      '📈 Statistic':'get_stat',
                      '🐵 Listen to all message':'all_mode_on',
                      '🙈 Listen only to commands':'all_mode_off',
                      '⌨️ Review Keyboar':'startall',
                      '↩️ Back':'start'}


HELP_TEXT = """❓ Help

🔍 To find music enter '/find [track_title]' or '/f [track_title]' and send it.

👑 /popular or /chart to find most popular songs.

🆕 /new_songs to find novelties songs.

For admins:
🙈 You can enable the 'all listen' mode in /settings.
🐵 To search music in this mode, you can just enter '[track_title]' and send it.

/about me c:
"""

ABOUT_TEXT = """📔 About!

📫 For any questions: @dashed_man
🍰 For donates: https://www.donationalerts.com/r/dashed_man

py3.8"""

WAITING_ANIM_LIST = "|\\-/"
WAITING_ANIM_LIST2 = "+x"

def waiting_animation():
    index = -1
    while True:
        index = (index+1)%4
        yield WAITING_ANIM_LIST[index]

def waiting_animation2():
    index = -1
    while True:
        index = (index+1)%2
        yield WAITING_ANIM_LIST2[index]
