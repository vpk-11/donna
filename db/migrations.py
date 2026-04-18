from db.database import Base, engine
import models.orm  # noqa: F401 — ensures all models are registered


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
