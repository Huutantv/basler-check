import sys
from PyInstaller.__main__ import run

run(["gui_qt.py",
     "--noconfirm", "--clean",
     "--onefile", "--windowed",
     "--name", "GEVConsole",
     "--icon", "app_icon.ico",
     "--version-file", "version_info.txt",
     "--add-data", "app_icon.ico" + ";" + ".",
     "--hidden-import", "snapshot",
     "--hidden-import", "gigetools",
     "--collect-all", "pypylon",
     "--exclude-module", "PyQt5",
     "--exclude-module", "tkinter"])
print("BUILD_DONE")
