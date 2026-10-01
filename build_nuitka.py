import sys
from nuitka.__main__ import main

sys.argv = ["nuitka"] + ["gui_qt.py",
      "--standalone",
      "--onefile",
      "--assume-yes-for-downloads",
      "--enable-plugin=pyside6",
      "--enable-plugin=numpy",
      "--include-package=pypylon",
      "--include-package-data=pypylon",
      "--include-data-file=app_icon.ico=app_icon.ico",
      "--windows-console-mode=disable",
      "--windows-icon-from-ico=app_icon.ico",
      "--windows-company-name=Factory Automation",
      "--windows-product-name=GEV Console",
      "--windows-file-version=1.0.0.0",
      "--windows-product-version=1.0.0.0",
      "--windows-file-description=GEV Console - GigE Vision camera network tool",
      "--output-dir=dist_nuitka",
      "--output-filename=GEVConsole.exe"]

main()
print("NUITKA_DONE")
