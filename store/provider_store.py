from sqlalchemy.orm import Session
from models.orm import Provider


class ProviderStore:
    def __init__(self, db: Session):
        self.db = db

    def get_by_phone(self, phone_number: str) -> Provider | None:
        return self.db.query(Provider).filter(Provider.phone_number == phone_number).first()

    def get_first(self) -> Provider | None:
        return self.db.query(Provider).first()

    def get(self, provider_id: int) -> Provider | None:
        return self.db.query(Provider).filter(Provider.id == provider_id).first()

    def create(self, data: dict) -> Provider:
        provider = Provider(**data)
        self.db.add(provider)
        self.db.commit()
        self.db.refresh(provider)
        return provider

    def update(self, provider_id: int, data: dict) -> Provider | None:
        provider = self.get(provider_id)
        if not provider:
            return None
        for key, value in data.items():
            setattr(provider, key, value)
        self.db.commit()
        self.db.refresh(provider)
        return provider
