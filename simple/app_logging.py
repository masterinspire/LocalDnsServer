import logging.config
import logging.handlers
import sys
from datetime import date
from logging import LogRecord
from os import PathLike
from pathlib import Path
from typing import Optional


class CustomFileHandler(logging.FileHandler):
    def __init__(self, directory: str | PathLike[str]):
        self.date_format = "%Y-%m-%d"
        self.filename_template = "{}.log"
        self.today = date.today()
        self.path = Path(directory)
        filename = self._format_filename()
        super().__init__(filename, encoding="utf-8", delay=True)

    def _format_filename(self):
        f = self.filename_template.format(self.today.strftime(self.date_format))
        return str(self.path.joinpath(f))

    def emit(self, record: LogRecord) -> None:
        if (today := date.today()) != self.today:
            self.today = today
            if self.stream is not None and not self.stream.closed:
                self.stream.close()
                # noinspection PyTypeChecker
                self.stream = None

            self.baseFilename = self._format_filename()

        if self.stream is None:
            self.path.mkdir(exist_ok=True, parents=True)

        super().emit(record)


def setup_logging_config(current_dir_data: Optional[Path] = None, console: Optional[bool] = None):
    # noinspection SpellCheckingInspection
    log_config = {
        "version": 1,
        "root": {"handlers": ["console"], "level": "DEBUG"},
        "loggers": {
            "hpack": {"handlers": ["null"], "propagate": False},
            "httpx": {"handlers": ["null"], "propagate": False},
        },
        "handlers": {
            "null": {"class": "logging.NullHandler"},
            "console": {"formatter": "default", "class": "logging.StreamHandler", "level": "DEBUG"},
        },
        "formatters": {
            "default": {
                "format": "{asctime}.{msecs:04.0f}|{levelname}|{name}|{message}",
                "datefmt": "%Y-%m-%d %H:%M:%S",
                "style": "{",
            }
        },
    }

    if console is False:
        log_config["root"]["handlers"].remove("console")
        del log_config["handlers"]["console"]

    if current_dir_data is not None:
        log_config["root"]["handlers"].append("file")
        log_config["handlers"]["file"] = {
            "formatter": "default",
            "class": ".".join([CustomFileHandler.__module__, CustomFileHandler.__qualname__]),
            "level": "DEBUG",
            "directory": current_dir_data.joinpath("temp", "logs"),
        }

    # noinspection SpellCheckingInspection
    sys.excepthook = custom_except_hook

    logging.config.dictConfig(log_config)


# noinspection PyUnusedLocal
def custom_except_hook(type1, value1, traceback1):
    # AttributeError: 'NoneType' object has no attribute 'flush'
    if isinstance(value1, AttributeError) and str(value1).find("'NoneType' object has no attribute 'flush'") != -1:
        return

    logger = logging.getLogger()
    logger.error(msg="custom_except_hook", exc_info=value1)
