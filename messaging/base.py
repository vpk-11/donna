from abc import ABC, abstractmethod


class MessagingClient(ABC):
    @abstractmethod
    async def send_to_admin(self, message: str) -> None: ...

    @abstractmethod
    async def send_to_phone(self, phone: str, message: str) -> None: ...
