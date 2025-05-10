import os

from configparser import ConfigParser

# internal lib
from tg_vk_music_bot import MusicBot
from tg_vk_music_bot import ui_constants as uic
from tg_vk_music_bot.log_lib import get_logger


if __name__ == "__main__":
    config_path = "../config.ini"
    if not os.path.exists(config_path):
        print(uic.NO_CONFIG_MESSAGE)
        exit()
    configs = ConfigParser()
    configs.read(config_path)

    # loggining
    logger = get_logger(
        configs['logging'].getint('level'),
        configs['logging'].getint('backup_length')
    )

    # if main then start bot
    bot = MusicBot(configs, logger)
    bot.start()
