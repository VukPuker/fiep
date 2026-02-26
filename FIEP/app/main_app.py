# FIEP/app/main_app.py

from FIEP.core.identity import Identity
from FIEP.network.transport import TransportLayer, NetworkMode
from FIEP.core.config import config
from FIEP.app.contacts import ContactStore
from FIEP.app.storage import MessageStorage
from FIEP.app.messenger import Messenger


class FIEPApp:
    def __init__(self, password_provider=None):
        # 1) профиль / активация
        self.identity = Identity(base_path="data")
        self.identity.load_or_activate()

        # 2) контакты и история
        self.contacts = ContactStore(base_path="data")
        self.storage = MessageStorage(base_path="data")

        # 3) транспорт
        self.transport = TransportLayer(
            config=config,
            identity=self.identity,
            password_provider=password_provider,
        )

        # 4) messenger-слой
        self.messenger = Messenger(
            identity=self.identity,
            transport=self.transport,
            contacts=self.contacts,
            storage=self.storage,
        )

    def start_network(self, mode: str = NetworkMode.RELAY):
        self.transport.start(mode=mode)

    def stop_network(self):
        self.transport.stop()
