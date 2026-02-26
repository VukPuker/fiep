# FIEP/ui/chat_view.py

from PyQt5 import QtWidgets, QtCore
from FIEP.app.message_model import InnerMessage


class ChatView(QtWidgets.QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.current_fp = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # заголовок
        self.header = QtWidgets.QLabel("Выберите контакт")
        self.header.setStyleSheet("font-size: 18px; padding: 10px;")
        layout.addWidget(self.header)

        # список сообщений
        self.messages = QtWidgets.QTextEdit()
        self.messages.setReadOnly(True)
        layout.addWidget(self.messages, 1)

        # поле ввода
        input_layout = QtWidgets.QHBoxLayout()
        self.input = QtWidgets.QTextEdit()
        self.input.setFixedHeight(60)
        self.send_btn = QtWidgets.QPushButton("Отправить")
        self.send_btn.clicked.connect(self.send_message)

        input_layout.addWidget(self.input, 1)
        input_layout.addWidget(self.send_btn)
        layout.addLayout(input_layout)

    def load_chat(self, fp, nickname):
        self.current_fp = fp
        self.header.setText(nickname or fp)

        self.messages.clear()
        history = self.app.messenger.get_history(fp)
        for rec in history:
            msg = InnerMessage.from_dict(rec["message"])
            self.append_message(fp, msg, direction=rec["direction"])

    def append_message(self, fp, msg, direction="in"):
        if direction == "in":
            prefix = f"{fp}: "
        else:
            prefix = "Вы: "

        self.messages.append(f"{prefix}{msg.text}")

    def send_message(self):
        if not self.current_fp:
            return

        text = self.input.toPlainText().strip()
        if not text:
            return

        self.app.messenger.send_text(self.current_fp, text)
        self.input.clear()
