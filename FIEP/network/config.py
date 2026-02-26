from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class Config:
    """
    Глобальная конфигурация FIEP.
    Безопасная, portable-версия, не создающая директории при импорте.
    """

    # ---------------------------------------------------------
    # ОСНОВНЫЕ ПУТИ
    # ---------------------------------------------------------

    # Базовая директория данных (может быть переопределена)
    DATA_DIR: Path = Path.home() / ".fiep"

    CONFIG_FILE: Path = None
    KEY_FILE: Path = None
    CONTACTS_FILE: Path = None

    MESSAGES_DIR: Path = None
    OFFLINE_DIR: Path = None

    # DAG хранится рядом с network/
    DAG_FILE: Path = Path(__file__).resolve().parent / "dag.json"

    # ---------------------------------------------------------
    # СЕТЕВЫЕ НАСТРОЙКИ
    # ---------------------------------------------------------

    RELAY_PORT_DEFAULT: int = 50860

    CENTRAL_RELAY_HOST: str = "109.124.215.78"
    CENTRAL_RELAY_PORT: int = 50861

    BOOTSTRAP_NODES: List[str] = field(default_factory=list)
    AUTO_SAVE_BOOTSTRAP: bool = True
    MAX_BOOTSTRAP_NODES: int = 50

    # ---------------------------------------------------------
    # ПОВЕДЕНИЕ СЕТИ
    # ---------------------------------------------------------

    DEBUG: bool = True
    ENABLE_WEBRTC: bool = True
    ENABLE_UDP: bool = True
    ENABLE_TOR: bool = True
    ENABLE_DHT: bool = True

    # ---------------------------------------------------------
    # РЕЖИМЫ
    # ---------------------------------------------------------

    TEST_MODE: bool = False  # тесты не должны писать в систему

    # ---------------------------------------------------------
    # ИНИЦИАЛИЗАЦИЯ
    # ---------------------------------------------------------

    def __post_init__(self):
        """
        Безопасная инициализация путей.
        Никаких mkdir() при импорте — только подготовка.
        """

        self.CONFIG_FILE = self.DATA_DIR / "config.json"
        self.KEY_FILE = self.DATA_DIR / "identity.enc"
        self.CONTACTS_FILE = self.DATA_DIR / "contacts.enc"

        self.MESSAGES_DIR = self.DATA_DIR / "messages"
        self.OFFLINE_DIR = self.DATA_DIR / "offline"

    # ---------------------------------------------------------
    # ЯВНАЯ ИНИЦИАЛИЗАЦИЯ ДИРЕКТОРИЙ
    # ---------------------------------------------------------

    def ensure_dirs(self):
        """
        Создаёт директории, но только если не TEST_MODE.
        Вызывается вручную из main(), а не при импорте.
        """
        if self.TEST_MODE:
            print("[Config] TEST_MODE: директории не создаются.")
            return

        try:
            self.DATA_DIR.mkdir(parents=True, exist_ok=True)
            self.MESSAGES_DIR.mkdir(parents=True, exist_ok=True)
            self.OFFLINE_DIR.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"[Config] Warning: failed to initialize directories: {e}")


# Глобальный объект конфигурации
config = Config()




