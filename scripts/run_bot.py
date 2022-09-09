import os
from dataclasses import dataclass

from configparser import ConfigParser


# internal lib
from root import MusicBot
import root.ui_constants as uic
from root.log_lib import get_logger


# constants
@dataclass(frozen=True)
class Constants:
    MEGABYTE_SIZE = 1 << 20
    MUSIC_LIST_LENGTH = 5


if __name__ == "__main__":
    constants = Constants()

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
    bot = MusicBot(constants, configs, logger)
    bot.start()
