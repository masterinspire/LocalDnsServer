import fnmatch
import platform
from pathlib import Path
from typing import Optional

from PyInstaller.building.api import PYZ, EXE, COLLECT
from PyInstaller.building.build_main import Analysis
from PyInstaller.building.datastruct import TOC


def file_version_info() -> Optional[str]:
    # noinspection SpellCheckingInspection
    file_version_info_txt = """
VSVersionInfo(
    ffi=FixedFileInfo(
        # filevers and prodvers should be always a tuple with four items: (1, 2, 3, 4)
        # Set not needed items to zero 0.
        filevers=(0, 1, 0, 0),
        prodvers=(0, 1, 0, 0),
        # Contains a bitmask that specifies the valid bits 'flags'r
        mask=0x3F,
        # Contains a bitmask that specifies the Boolean attributes of the file.
        flags=0x0,
        # The operating system for which this file was designed.
        # 0x4 - NT and there is no need to change it.
        OS=0x4,
        # The general type of file.
        # 0x1 - the file is an application.
        fileType=0x1,
        # The function of the file.
        # 0x0 - the function is not defined for this fileType
        subtype=0x0,
        # Creation date and time stamp.
        date=(0, 0),
    ),
    kids=[
        VarFileInfo([VarStruct("Translation", [0, 1200])]),
        StringFileInfo(
            [
                StringTable(
                    "000004b0",
                    [
                        StringStruct("Comments", "Local Dns Server"),
                        StringStruct("CompanyName", ""),
                        StringStruct("FileDescription", "Local Dns Server"),
                        StringStruct("FileVersion", "0.1.0.0"),
                        StringStruct("InternalName", ""),
                        StringStruct("LegalCopyright", ""),
                        StringStruct("OriginalFilename", ""),
                        StringStruct("ProductName", "LocalDnsServer"),
                        StringStruct("ProductVersion", "0.1.0.0"),
                        StringStruct("Assembly Version", "0.1.0.0"),
                    ],
                )
            ]
        ),
    ],
)
    """.strip()
    # noinspection PyUnresolvedReferences
    p = Path(workpath).joinpath("file_version_info.txt")
    with open(p, mode="w") as f:
        f.write(file_version_info_txt)

    return str(p) if platform.system() == "Windows" else None


name = "LocalDnsServer"

block_cipher = None

# https://pyinstaller.org/en/stable/spec-files.html#globals-available-to-the-spec-file

a = Analysis(
    ["simple/__main__.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# noinspection DuplicatedCode
data_patterns_to_exclude = [
    r"cryptography-*.dist-info[\/]*",
    r"*[\/]py.typed",
]
data_items_to_remove = []
for w in a.datas:
    for pattern in data_patterns_to_exclude:
        if fnmatch.fnmatch(str(w[0]), pattern):
            data_items_to_remove.append(w)
            break

a.datas = a.datas - TOC(data_items_to_remove)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=file_version_info(),
    icon="NONE",
    uac_admin=True,
    uac_uiaccess=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=name,
)
