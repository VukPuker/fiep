import sys
import os
from identity import generate_identity
import json
from PyQt5 import QtWidgets, QtCore

from profile_builder import build_profile, encrypt_profile_with_activation
from usb_tools import (
    list_removable_drives,
    get_usb_id,
    copy_portable_template,
    write_profile_enc,
    write_activation_key,
    write_portable_config,
)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates", "fiep_portable")

# ---------------------------------------------------------
# Главное окно Issuer
# ---------------------------------------------------------

class IssuerWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FIEP Issuer")
        self.setMinimumSize(600, 450)

        self.drives = []
        self.init_ui()
        self.refresh_drives()

    # -----------------------------------------------------
    # UI
    # -----------------------------------------------------

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # Список флешек
        layout.addWidget(QtWidgets.QLabel("Выберите флешку:"))
        self.drives_list = QtWidgets.QListWidget()
        layout.addWidget(self.drives_list)

        # USB-ID
        self.usb_id_label = QtWidgets.QLabel("USB-ID: —")
        layout.addWidget(self.usb_id_label)

        # Прогресс-бар
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 9)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        # Кнопки
        btn_layout = QtWidgets.QHBoxLayout()
        self.refresh_btn = QtWidgets.QPushButton("Обновить список")
        self.create_btn = QtWidgets.QPushButton("Создать дистрибутив")
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addWidget(self.create_btn)
        layout.addLayout(btn_layout)

        # Лог
        layout.addWidget(QtWidgets.QLabel("Лог:"))
        self.log = QtWidgets.QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        # Сигналы
        self.refresh_btn.clicked.connect(self.refresh_drives)
        self.create_btn.clicked.connect(self.on_create_clicked)
        self.drives_list.currentItemChanged.connect(self.on_drive_selected)

    # -----------------------------------------------------
    # Лог
    # -----------------------------------------------------

    def log_msg(self, text: str):
        self.log.append(text)
        self.log.moveCursor(self.log.textCursor().End)

    # -----------------------------------------------------
    # Работа со списком флешек
    # -----------------------------------------------------

    def refresh_drives(self):
        self.drives_list.clear()
        self.drives = list_removable_drives()

        if not self.drives:
            self.log_msg("Съёмные диски не найдены.")
            self.usb_id_label.setText("USB-ID: —")
            return

        for d in self.drives:
            item_text = f"{d['mount']}  ({d['label']})"
            item = QtWidgets.QListWidgetItem(item_text)
            item.setData(QtCore.Qt.UserRole, d)
            self.drives_list.addItem(item)

        self.log_msg("Список флешек обновлён.")

    def get_selected_drive(self):
        item = self.drives_list.currentItem()
        if not item:
            return None
        return item.data(QtCore.Qt.UserRole)

    def on_drive_selected(self):
        drive = self.get_selected_drive()
        if not drive:
            self.usb_id_label.setText("USB-ID: —")
            return

        usb_id = get_usb_id(drive["mount"])
        self.usb_id_label.setText(f"USB-ID: {usb_id}")

    # -----------------------------------------------------
    # Проверка: флешка пуста?
    # -----------------------------------------------------

    def is_drive_empty(self, path):
        try:
            return len(os.listdir(path)) == 0
        except:
            return False

    # -----------------------------------------------------
    # Создание дистрибутива
    # -----------------------------------------------------

    def on_create_clicked(self):
        drive = self.get_selected_drive()
        if not drive:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Не выбрана флешка.")
            return

        mount = drive["mount"]

        # Проверка: флешка не пуста
        if not self.is_drive_empty(mount):
            reply = QtWidgets.QMessageBox.warning(
                self,
                "Флешка не пуста",
                "На флешке уже есть файлы.\nПродолжить и перезаписать?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            if reply != QtWidgets.QMessageBox.Yes:
                return

        # Подтверждение
        reply = QtWidgets.QMessageBox.question(
            self,
            "Подтверждение",
            f"Создать дистрибутив на флешке {mount}?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return

        try:
            self.create_distribution(mount)
            QtWidgets.QMessageBox.information(self, "Готово", "Дистрибутив успешно создан.")
        except Exception as e:
            self.log_msg(f"Ошибка: {e}")
            QtWidgets.QMessageBox.critical(self, "Ошибка", str(e))

    # -----------------------------------------------------
    # Основная логика создания дистрибутива
    # -----------------------------------------------------

    def create_distribution(self, target_drive: str):
        self.progress.setValue(0)
        self.log_msg(f"Создание дистрибутива на {target_drive}...")

        # 1. Проверка шаблона
        if not os.path.isdir(TEMPLATE_DIR):
            raise RuntimeError(f"Не найден шаблон FIEP: {TEMPLATE_DIR}")

        # 2. Генерация identity
        self.log_msg("Генерация identity...")
        self.progress.setValue(1)
        ident = generate_identity()

        # 3. Сборка профиля
        self.log_msg("Сборка профиля...")
        self.progress.setValue(2)
        profile = build_profile(
            identity_public=ident["public_key"],
            identity_private=ident["private_key"],
            fingerprint=ident["fingerprint"],
            peer_id=ident["peer_id"],
        )

        # 4. Шифрование профиля
        self.log_msg("Шифрование профиля...")
        self.progress.setValue(3)
        activation_b32, profile_enc, storage_key = encrypt_profile_with_activation(profile)

        # 5. Копирование портативного FIEP
        self.log_msg("Копирование портативного FIEP...")
        self.progress.setValue(4)
        copy_portable_template(TEMPLATE_DIR, target_drive)

        # 6. Запись profile.enc
        self.log_msg("Запись profile.enc...")
        self.progress.setValue(5)
        write_profile_enc(target_drive, profile_enc)

        # 7. Запись activation.key
        self.log_msg("Запись activation.key...")
        self.progress.setValue(6)
        write_activation_key(target_drive, activation_b32)

        # 8. Получение USB-ID
        self.log_msg("Получение USB-ID...")
        self.progress.setValue(7)
        usb_id = get_usb_id(target_drive)
        self.log_msg(f"USB-ID: {usb_id}")

        # 9. Запись конфигурации
        self.log_msg("Запись fiep_portable_config.json...")
        self.progress.setValue(8)
        write_portable_config(target_drive, usb_id)

        # Завершено
        self.progress.setValue(9)
        self.log_msg("Готово.")


# ---------------------------------------------------------
# Точка входа
# ---------------------------------------------------------

def main():
    app = QtWidgets.QApplication(sys.argv)
    w = IssuerWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
