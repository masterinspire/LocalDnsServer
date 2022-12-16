import logging
import sys
import time
from typing import cast

import servicemanager
import win32service
import win32serviceutil
import winerror

from simple.app_args import AppArgs

logger = logging.getLogger(__name__)


class DnsServerWindowsService(win32serviceutil.ServiceFramework):
    """
    https://thepythoncorner.com/posts/2018-08-01-how-to-create-a-windows-service-in-python/
    https://stackoverflow.com/questions/32404/how-do-you-run-a-python-script-as-a-service-in-windows
    https://metallapan.se/post/windows-service-pywin32-pyinstaller/
    """

    _svc_name_ = "LocalDnsServer"
    _svc_description_ = "Local Dns Server"
    _svc_display_name_ = "Local Dns Server"
    _exe_name_ = sys.executable
    app_args: AppArgs  # __handle_run

    def __init__(self, args):
        super().__init__(args)
        self.is_running = False

    # noinspection PyPep8Naming
    def SvcDoRun(self):
        self.ReportServiceStatus(win32service.SERVICE_START_PENDING)
        self.is_running = True
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)

        try:
            self.__server_loop()
        except Exception as e:
            logger.critical(msg="PARTY CRASHED", exc_info=e)
            time.sleep(0.5)

    def __server_loop(self):
        from simple.dns_server import start_server
        from simple.single_instance import single_instance_locker

        with single_instance_locker(self.app_args) as running:
            if running:
                return

            with start_server(self.app_args):
                while True:
                    if not self.is_running:
                        break

                    try:
                        time.sleep(1)
                    except (KeyboardInterrupt, EOFError):
                        break

    # noinspection PyPep8Naming
    def SvcStop(self):
        self.is_running = False
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.ReportServiceStatus(win32service.SERVICE_STOPPED)

    # noinspection PyPep8Naming
    def SvcShutdown(self):
        self.is_running = False
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.ReportServiceStatus(win32service.SERVICE_STOPPED)


class HandleWindowsServiceCommandLine:
    def __init__(self, app_args: AppArgs):
        self.app_args = app_args

    def __try_handle_error(self, e: Exception, error_type: int) -> bool:
        import pywintypes

        # noinspection PyUnresolvedReferences
        if isinstance(e, pywintypes.error):
            # noinspection PyUnresolvedReferences
            e = cast(pywintypes.error, e)
            return e.winerror == error_type

        return False

    def __handle_install(self):
        # noinspection PyProtectedMember
        service_config = {
            "pythonClassString": win32serviceutil.GetServiceClassString(DnsServerWindowsService),
            "serviceName": DnsServerWindowsService._svc_name_,
            "displayName": DnsServerWindowsService._svc_display_name_,
            "description": DnsServerWindowsService._svc_description_,
            "startType": win32service.SERVICE_AUTO_START,
            "bRunInteractive": False,
            "exeName": DnsServerWindowsService._exe_name_,
            "exeArgs": "--port {} --service run".format(self.app_args.port),
        }

        try:
            win32serviceutil.InstallService(**service_config)
            print("service installed")
        except Exception as e:
            if self.__try_handle_error(e, winerror.ERROR_SERVICE_EXISTS):
                try:
                    # noinspection PyProtectedMember
                    win32serviceutil.ChangeServiceConfig(**service_config)
                    print("service installed and updated")
                except Exception as e:
                    print(e)
            else:
                print(e)

    def __handle_start(self):
        try:
            # noinspection PyProtectedMember
            win32serviceutil.StartService(DnsServerWindowsService._svc_name_)
        except Exception as e:
            print(e)
        else:
            print("service started")

    def __handle_stop(self):
        try:
            # noinspection PyProtectedMember
            win32serviceutil.StopService(DnsServerWindowsService._svc_name_)
        except Exception as e:
            print(e)
        else:
            print("service stopped")

    def __handle_restart(self):
        try:
            # noinspection PyProtectedMember
            win32serviceutil.RestartService(DnsServerWindowsService._svc_name_)
        except Exception as e:
            print(e)
        else:
            print("service restarted")

    def __handle_run(self):
        DnsServerWindowsService.app_args = self.app_args
        try:
            servicemanager.Initialize()
            servicemanager.PrepareToHostSingle(DnsServerWindowsService)
            servicemanager.StartServiceCtrlDispatcher()
        except Exception as e:
            logger.error(msg="run", exc_info=e)

    def __handle_remove(self):
        try:
            # noinspection PyProtectedMember
            win32serviceutil.StopService(DnsServerWindowsService._svc_name_)
        except Exception:
            pass
        else:
            print("service stopped")

        try:
            # noinspection PyProtectedMember
            win32serviceutil.RemoveService(DnsServerWindowsService._svc_name_)
        except Exception as e:
            print(e)
        else:
            print("service removed")

    def handle_command_line(self) -> bool:
        match self.app_args.service:
            case "install":
                self.__handle_install()
            case "start":
                self.__handle_start()
            case "stop":
                self.__handle_stop()
            case "restart":
                self.__handle_restart()
            case "run":
                self.__handle_run()
            case "remove":
                self.__handle_remove()
            case _:
                return False

        return True
