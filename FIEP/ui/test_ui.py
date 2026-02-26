import os
import sys

# Путь к текущей папке ui/
UI_DIR = os.path.dirname(os.path.abspath(__file__))

# Путь к каталогу, содержащему пакет FIEP (D:\FIEP)
PROJECT_PARENT = os.path.abspath(os.path.join(UI_DIR, "..", ".."))

# Добавляем путь к корню проекта в sys.path
if PROJECT_PARENT not in sys.path:
    sys.path.insert(0, PROJECT_PARENT)

# Теперь импорт FIEP.* работает
from PyQt5 import QtWidgets
from FIEP.ui.main_window import MainWindow


# --- Моки для запуска UI без ядра ---
class MockMessenger:
    def on_message(self, cb): pass
    def send_text(self, fp, text): print("[MOCK] send:", fp, text)
    def get_history(self, fp): return []


class MockContacts:
    def all(self): return []
    def get(self, fp): return None


class MockTransport:
    def start(self, mode=None): pass
    def stop(self): pass


class MockIdentity:
    fingerprint = "mock_fp"
    peer_id = "mock_peer"


class MockFIEPApp:
    def __init__(self):
        self.identity = MockIdentity()
        self.contacts = MockContacts()
        self.messenger = MockMessenger()
        self.transport = MockTransport()

    def start_network(self, mode=None): pass
    def stop_network(self): pass


class TestMainWindow(MainWindow):
    def __init__(self):
        super().__init__()
        self.app = MockFIEPApp()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    w = TestMainWindow()
    w.show()
    sys.exit(app.exec_())
