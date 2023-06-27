import logging
import queue
import threading
import time
from contextlib import contextmanager
from typing import Callable

import dns.exception
import dns.message
import dns.query
import dns.rdata
import dns.rdtypes
import dns.rdtypes.IN
import dns.rdtypes.IN.A
import dns.rdtypes.IN.AAAA
import dns.resolver
import httpx

from simple import USER_AGENT
from simple.app_args import AppArgs
from simple.db import TheDbJob
from simple.models import DnsServerConfig
from simple.threading_server import ThreadingDnsTCPServer, ThreadingDnsUDPServer

logger = logging.getLogger(__name__)


@contextmanager
def __start_threading_dns_server(
    threading_server_class: Callable[[tuple[str, int], DnsServerConfig, httpx.Client], ThreadingDnsTCPServer | ThreadingDnsUDPServer],
    server_address: tuple[str, int],
    config: DnsServerConfig,
    doh_client: httpx.Client,
):
    server = threading_server_class(server_address, config, doh_client)
    server_thread_name = "{}_{}".format(type(server).__name__, server_address)
    server_thread = threading.Thread(target=server.serve_forever, name=server_thread_name)
    server_thread.daemon = True
    server_thread.start()

    try:
        yield
    finally:
        server.shutdown()
        server_thread.join()


@contextmanager
def handle_request_log_queue():
    finished = threading.Event()

    def handle_it():
        try:
            db = TheDbJob()
            while True:
                try:
                    item = TheDbJob.request_log_queue.get(block=True, timeout=0.1)
                except queue.Empty:
                    if finished.is_set():
                        break
                else:
                    try:
                        db.insert_request_log(item)
                    except Exception as ee:
                        logger.error("insert_request_log", exc_info=ee)
                    finally:
                        TheDbJob.request_log_queue.task_done()
        except Exception as e:
            logger.error("handle_request_log_queue", exc_info=e)

    request_log_thread = threading.Thread(target=handle_it, name="request_log_thread")
    request_log_thread.daemon = True
    request_log_thread.start()

    try:
        yield
    finally:
        TheDbJob.request_log_queue.join()
        finished.set()
        request_log_thread.join()


@contextmanager
def start_server(app_args: AppArgs):
    from simple.config import ConfigFile

    config_file = ConfigFile(app_args)
    config = config_file.read_config_from_config_file()
    config_file.init_db_from_config(config)

    server_address_ipv4 = ("0.0.0.0", app_args.port)
    server_address_ipv6 = ("::", app_args.port)
    with (
        httpx.Client(http1=True, http2=True, headers={"User-Agent": USER_AGENT}, timeout=2, trust_env=False) as doh_client,
        handle_request_log_queue(),
        __start_threading_dns_server(ThreadingDnsTCPServer, server_address_ipv4, config, doh_client),
        __start_threading_dns_server(ThreadingDnsTCPServer, server_address_ipv6, config, doh_client),
        __start_threading_dns_server(ThreadingDnsUDPServer, server_address_ipv4, config, doh_client),
        __start_threading_dns_server(ThreadingDnsUDPServer, server_address_ipv6, config, doh_client),
    ):
        logger.info("Local Dns Server at {} and {} is up and running".format(server_address_ipv4, server_address_ipv6))
        yield


def query_input_loop(port: int):
    while True:
        try:
            query = input(">>> query: ")
        except (KeyboardInterrupt, EOFError):
            break
        else:
            if not query or query in ["exit", "bye"]:
                break

            query1 = query.split(":")
            if len(query1) == 1:
                query1.append("A")

            domain, type1 = query1
            try:
                r = dns.query.tcp(dns.message.make_query(domain, rdtype=type1), where="127.0.0.1", port=port)
                print("========================= response")
                print(r)
                print()
            except Exception as err:
                print("========================= error")
                print(str(err))
                print()


def do_action_dns_server(app_args: AppArgs):
    from simple import is_running_in_windows, is_running_in_pyinstaller_bundle

    if is_running_in_windows and is_running_in_pyinstaller_bundle:
        from simple.windows_service import HandleWindowsServiceCommandLine

        if HandleWindowsServiceCommandLine(app_args).handle_command_line():
            return

    from simple.single_instance import single_instance_locker

    with single_instance_locker(app_args) as running:
        if not running:
            with start_server(app_args):
                time.sleep(0.1)
                query_input_loop(app_args.port)
