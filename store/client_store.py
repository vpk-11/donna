from sqlalchemy.orm import Session
from models.orm import Client


class ClientStore:
    def __init__(self, db: Session):
        self.db = db

    def get(self, client_id: int) -> Client | None:
        return self.db.query(Client).filter(Client.id == client_id).first()

    def get_by_phone(self, phone_number: str) -> Client | None:
        return self.db.query(Client).filter(Client.phone_number == phone_number).first()

    def get_by_name(self, name: str, provider_id: int) -> Client | None:
        return (
            self.db.query(Client)
            .filter(Client.provider_id == provider_id, Client.name.ilike(f"%{name}%"))
            .first()
        )

    def list_by_provider(self, provider_id: int) -> list[Client]:
        return self.db.query(Client).filter(Client.provider_id == provider_id).all()

    def create(self, data: dict) -> Client:
        client = Client(**data)
        self.db.add(client)
        self.db.commit()
        self.db.refresh(client)
        return client

    def update(self, client_id: int, data: dict) -> Client | None:
        client = self.get(client_id)
        if not client:
            return None
        for key, value in data.items():
            setattr(client, key, value)
        self.db.commit()
        self.db.refresh(client)
        return client
