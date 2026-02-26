# FIEP/ui/contacts_view.py

from PyQt5 import QtWidgets, QtCore


class ContactsView(QtWidgets.QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.on_contact_selected = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # поиск
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Поиск...")
        layout.addWidget(self.search)

        # список контактов
        self.list = QtWidgets.QListWidget()
        self.list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list, 1)

        self.reload_contacts()

    def reload_contacts(self):
        self.list.clear()
        for c in self.app.contacts.all():
            item = QtWidgets.QListWidgetItem(c.nickname or c.fingerprint)
            item.setData(QtCore.Qt.UserRole, c)
            self.list.addItem(item)

    def update_last_message(self, fp, msg):
        # можно добавить отображение последнего сообщения
        pass

    def _on_item_clicked(self, item):
        c = item.data(QtCore.Qt.UserRole)
        if self.on_contact_selected:
            self.on_contact_selected(c.fingerprint, c.nickname)
