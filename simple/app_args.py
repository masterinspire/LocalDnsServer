import argparse
import sys
import traceback
from pathlib import Path

from simple import is_running_in_pyinstaller_bundle
from simple.models import AppArgs


def setup_argparse() -> AppArgs:
    try:
        current_dir = Path(sys.executable).resolve().parent if is_running_in_pyinstaller_bundle else Path(__file__).resolve().parent.parent
        current_dir_data = current_dir.joinpath("data")
    except Exception:
        traceback.print_exc()
        sys.exit()

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=current_dir_data, help="directory for config files and temp files. default: data")
    parser.add_argument("--port", type=int, default=53, help="which port the server should listen, default: 53")
    parser.add_argument(
        "--service", type=str, choices=["install", "start", "stop", "remove", "restart", "run"], help="windows only. manage windows service"
    )
    args, _ = parser.parse_known_args()
    args = vars(args)
    result = AppArgs(**args)

    return result


app_args = setup_argparse()
