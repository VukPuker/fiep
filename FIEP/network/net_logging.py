import logging
from pathlib import Path
from FIEP.network.config import config

def get_network_logger(name: str = "FIEP.network") -> logging.Logger:
    """
    Возвращает настроенный логгер для сетевых модулей FIEP.
    Логгер:
      - пишет в файл network.log
      - не дублирует хендлеры при повторных вызовах
      - не пропускает сообщения в root-логгер
    """
    
    
    log_dir: Path = config.DATA_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "network.log"

    logger = logging.getLogger(name)

    # Если уже настроен — просто возвращаем
    if getattr(logger, "_fiep_configured", False):
        return logger

    logger.setLevel(logging.INFO)

    # Файловый хендлер
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    logger.addHandler(file_handler)

    # (Опционально) консольный вывод — удобно при разработке
    if config.DEBUG:
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(
            "[%(levelname)s] %(name)s: %(message)s"
        ))
        logger.addHandler(console)

    # Не передавать сообщения в root
    logger.propagate = False

    # Помечаем, что логгер уже настроен
    logger._fiep_configured = True

    return logger
