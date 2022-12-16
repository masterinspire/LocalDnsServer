import logging
import time

try:
    from simple.app_args import setup_argparse, AppArgs, app_args

    app_args.data_dir.mkdir(exist_ok=True, parents=True)

    from simple import is_running_in_windows, is_running_in_pyinstaller_bundle
    from simple.app_logging import setup_logging_config

    setup_logging_config(None if is_running_in_windows and not is_running_in_pyinstaller_bundle else app_args.data_dir)

    from simple.dns_server import do_action_dns_server

    do_action_dns_server(app_args)
except Exception as e:
    logger = logging.getLogger(__name__)
    logger.critical(msg="PARTY CRASHED", exc_info=e)
    time.sleep(0.5)
