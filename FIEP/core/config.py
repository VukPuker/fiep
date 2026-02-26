# FIEP/core/config.py

class Config:
    """
    Конфигурация клиента FIEP.
    Используется TransportLayer и другими подсистемами.
    """

    # Центральный relay
    CENTRAL_RELAY_HOST = "relay.fiep.net"     # пример, можно заменить
    CENTRAL_RELAY_PORT = 443

    # Bootstrap-узлы DHT
    BOOTSTRAP_NODES = [
        "relay.fiep.net:443",
        # можно добавить дополнительные узлы
    ]

    # Режимы сети по умолчанию
    DEFAULT_NETWORK_MODE = "relay"

    # Путь к данным (identity.json, contacts.json, history/)
    DATA_DIR = "data"


# Глобальный объект конфигурации
config = Config()
