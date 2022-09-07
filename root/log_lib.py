import logging
from logging.handlers import RotatingFileHandler


def get_logger(level, backup_length):
    file_log = RotatingFileHandler(
        "bot.log",
        mode='a',
        maxBytes=20480,
        backupCount=backup_length
    )
    console_out = logging.StreamHandler()

    logging.basicConfig(  # noqa
        handlers=(file_log, console_out),
        format='[%(asctime)s | %(levelname)s] %(name)s: %(message)s',
        datefmt='%a %b %d %H:%M:%S %Y',
        level=level
    )
    logging.getLogger('aiohttp.access').setLevel(logging.WARNING)
    logging.getLogger('aiohttp.client').setLevel(logging.WARNING)
    logging.getLogger('aiohttp.internal').setLevel(logging.WARNING)
    logging.getLogger('aiohttp.server').setLevel(logging.WARNING)
    logging.getLogger('aiohttp.web').setLevel(logging.WARNING)
    logging.getLogger('aiohttp.websocket').setLevel(logging.WARNING)

    LOGGER = logging.getLogger("bot")