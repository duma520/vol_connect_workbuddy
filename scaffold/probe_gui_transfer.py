import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, r"G:\Python_Code\vol_connect_workbuddy")
from PySide6.QtWidgets import QApplication
from gui.transfer_dialog import ExportDialog, ImportDialog
from gui.main_window import MainWindow

app = QApplication([])
win = MainWindow(None)
print("MainWindow ok, buttons:", win.btn_export.text(), "/", win.btn_import.text())

dlg = ExportDialog(win)
print("ExportDialog rows:", dlg.list.count(), "summary:", dlg.summary.text())
print("Export default filename:", __import__("relay.transfer", fromlist=["x"]).default_export_name())

imp = ImportDialog(win)
print("ImportDialog regions:", [imp.combo_region.itemText(i) for i in range(imp.combo_region.count())])
print("Import button enabled before file:", imp.btn_import.isEnabled())
print("SMOKE OK")