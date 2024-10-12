import platform
import sys

# noinspection SpellCheckingInspection
is_running_in_pyinstaller_bundle = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
is_running_in_windows = platform.system() == "Windows"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"
