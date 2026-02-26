# FIEP/ui/main_window.py

from PyQt5 import QtWidgets, QtCore, QtGui
from FIEP.app.main_app import FIEPApp
from FIEP.ui.chat_view import ChatView
from FIEP.ui.contacts_view import ContactsView
from FIEP.ui.admin_panel import AdminPanel


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("FIEP Messenger")
        self.resize(1200, 700)

        # ядро приложения
        self.app = FIEPApp()
        self.app.start_network()

        # центральный виджет
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        layout = QtWidgets.QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        # левая панель
        self.contacts_view = ContactsView(self.app)
        layout.addWidget(self.contacts_view, 1)

        # правая панель (чат)
        self.chat_view = ChatView(self.app)
        layout.addWidget(self.chat_view, 3)

        # обработчик входящих сообщений
        self.app.messenger.on_message(self.on_message_received)

        # скрытая админ‑панель
        self.admin_panel = AdminPanel(self.app)
        self.admin_panel.hide()

        # хоткей для админ‑панели
        self._init_hotkeys()

        # сигнал выбора контакта
        self.contacts_view.on_contact_selected = self.chat_view.load_chat

    def _init_hotkeys(self):
        shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+Shift+D"), self)
        shortcut.activated.connect(self.toggle_admin_panel)

    def toggle_admin_panel(self):
        if self.admin_panel.isVisible():
            self.admin_panel.hide()
        else:
            self.admin_panel.show()

    def on_message_received(self, sender_fp, msg):
        # если открыт чат с этим контактом — обновляем
        if self.chat_view.current_fp == sender_fp:
            self.chat_view.append_message(sender_fp, msg)

        # обновляем список контактов (последнее сообщение)
        self.contacts_view.update_last_message(sender_fp, msg)
