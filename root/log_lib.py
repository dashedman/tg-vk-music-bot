import logging
from logging.handlers import RotatingFileHandler

import coloredlogs as coloredlogs


class Color:
    """ https://coloredlogs.readthedocs.io/en/latest/api.html#id28 """
    GREY = 8
    ORANGE = 214


def get_logger(level, backup_length) -> logging.Logger:
    FORMATTER_STR = '[%(asctime)s|%(name)s|%(levelname)s] %(message)s'

    level_colormap = {
        'critical': {'bold': True, 'color': 'red'},
        'debug': {'color': 'white', 'faint': True},
        'error': {'color': 'red'},
        'info': {'color': 'cyan'},
        'notice': {'color': 'magenta'},
        'spam': {'color': 'green', 'faint': True},
        'success': {'bold': True, 'color': 'green'},
        'verbose': {'color': 'blue'},
        'warning': {'color': Color.ORANGE}
    }
    field_colormap = {
        'asctime': {'color': 'green'},
        'hostname': {'color': 'magenta'},
        'levelname': {'bold': True, 'color': 'yellow'},
        'name': {'color': 'blue'},
        'programname': {'color': 'cyan'},
        'username': {'color': 'yellow'}
    }

    coloredlogs.install(
        level=level,
        fmt=FORMATTER_STR,
        level_styles=level_colormap,
        field_styles=field_colormap,
    )

    formatter = coloredlogs.ColoredFormatter(FORMATTER_STR)
    file_log = RotatingFileHandler(
        "bot.log",
        mode='a',
        maxBytes=20480,
        encoding='utf-8',
        backupCount=backup_length
    )
    file_log.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(file_log)

    logging.getLogger('aiohttp.access').setLevel(logging.WARNING)
    logging.getLogger('aiohttp.client').setLevel(logging.WARNING)
    logging.getLogger('aiohttp.internal').setLevel(logging.WARNING)
    logging.getLogger('aiohttp.server').setLevel(logging.WARNING)
    logging.getLogger('aiohttp.web').setLevel(logging.WARNING)
    logging.getLogger('aiohttp.websocket').setLevel(logging.WARNING)

    return logging.getLogger("bot")


if __name__ == '__main__':
    logger = get_logger(10, 2)
    logger.debug('debug test')
    logger.info('info test')
    logger.warning('warning test')
    logger.error('error test')
    logger.critical('critical test')
