import logging
import os
from contextlib import contextmanager

from simple import is_running_in_windows
from simple.models import AppArgs

logger = logging.getLogger(__name__)


@contextmanager
def single_instance_locker(app_args: AppArgs):
    """
    https://stackoverflow.com/questions/380870/make-sure-only-a-single-instance-of-a-program-is-running
    """
    lock1 = None
    lock2 = None

    if is_running_in_windows:
        import win32api
        import winerror
        import win32event

        lock1 = win32event.CreateMutex(None, True, "{4077E45D-7DA1-479D-A719-E4DC6814C2A5}")
        running = win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS
    else:
        import fcntl

        lock2 = os.open(app_args.data_dir.joinpath("lock.lock"), os.O_WRONLY)
        try:
            fcntl.lockf(lock2, fcntl.LOCK_EX | fcntl.LOCK_NB)
            running = False
        except IOError:
            running = True

    if running:
        logger.warning("An app has already started")

    try:
        yield running
    finally:
        try:
            if is_running_in_windows:
                if lock1:
                    import win32api

                    win32api.CloseHandle(lock1)
            else:
                if lock2:
                    os.close(lock2)
        except Exception:
            pass
