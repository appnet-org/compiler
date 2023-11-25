import logging

import colorlog

ELEMENT_LOG = logging.getLogger("ir")

loggers = [ELEMENT_LOG]


def init_logging(dbg: bool):
    level = logging.DEBUG if dbg else logging.INFO
    handler = colorlog.StreamHandler()
    handler.setFormatter(
        colorlog.ColoredFormatter(
            "%(log_color)s%(levelname)-7s%(reset)s %(purple)s%(name)-7s%(reset)s - %(message)s"
        )
    )
    for logger in loggers:
        logger.setLevel(level)
        logger.addHandler(handler)
