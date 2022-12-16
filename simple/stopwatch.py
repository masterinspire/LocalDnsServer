import time
from typing import Optional


class Stopwatch(object):
    def __init__(self):
        self.__s = None
        self.__enter_time = None
        self.__exit_time = None

    @property
    def elapsed_milliseconds(self) -> Optional[float]:
        return self.__s

    def __now(self):
        return time.perf_counter_ns()

    def __enter__(self):
        self.__enter_time = self.__now()
        self.__s = None
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.__exit_time = self.__now()
        self.__s = round((self.__exit_time - self.__enter_time) / 1000 / 1000, 2)
