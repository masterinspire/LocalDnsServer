import platform
from contextlib import suppress
from pathlib import Path

import PyInstaller.__main__
import PyInstaller.building.utils

# noinspection PyProtectedMember
__original_rmtree = PyInstaller.building.utils._rmtree


def patch_rmtree(path):
    with suppress(PermissionError):
        __original_rmtree(path)


PyInstaller.building.utils._rmtree = patch_rmtree

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
