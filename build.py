import platform
from pathlib import Path

import PyInstaller.__main__

if __name__ == "__main__":
    c = Path(__file__).resolve().parent
    build = c.joinpath("build")
    build.mkdir(exist_ok=True)
    # pyi-grab_version exe_file

    w = platform.system().lower()
    dist_path = str(build.joinpath(f"dist-{w}"))
    work_path = str(build.joinpath("temp"))
    spec_file = str(c.joinpath("build.spec"))

    # noinspection SpellCheckingInspection
    PyInstaller.__main__.run([str(spec_file), "-y", "--distpath", dist_path, "--workpath", work_path])

    print("\n===============================")
    print("\ndist path is {}".format(dist_path))
    print("\n===============================")
