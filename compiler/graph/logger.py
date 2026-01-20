import logging
import os

import colorlog

ELEMETN_LOG = logging.getLogger("Element Compiler")
GRAPH_LOG = logging.getLogger("Graph Compiler")
GRAPH_BACKEND_LOG = logging.getLogger("Graph Compiler Backend")
EVAL_LOG = logging.getLogger("Evaluation")
TEST_LOG = logging.getLogger("TEST")

loggers = [ELEMETN_LOG, GRAPH_LOG, GRAPH_BACKEND_LOG, EVAL_LOG, TEST_LOG]

# Project root for computing relative paths
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class RelativePathFormatter(colorlog.ColoredFormatter):
    """Custom formatter that shows file paths relative to project root."""

    def format(self, record):
        # Convert absolute pathname to relative path
        if record.pathname:
            try:
                record.relativepath = os.path.relpath(record.pathname, _PROJECT_ROOT)
            except ValueError:
                record.relativepath = record.pathname
        else:
            record.relativepath = record.filename
        return super().format(record)


def init_logging(dbg: bool):
    level = logging.DEBUG if dbg else logging.INFO
    handler = colorlog.StreamHandler()
    handler.setFormatter(
        RelativePathFormatter(
            "%(log_color)s%(levelname)-7s%(reset)s %(purple)s%(name)-7s%(reset)s - %(asctime)s - [%(relativepath)s:%(lineno)d] %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    for logger in loggers:
        logger.setLevel(level)
        logger.addHandler(handler)
