from messaging.base import MessagingClient

# V2: POST https://api.linq.app/v1/messages with body {"to": phone, "text": message}
# Auth via Bearer token in Authorization header (settings.linq_api_token).
# Inbound webhooks POST to /webhook/linq with {"from": phone, "text": message}.


class LinqMessagingClient(MessagingClient):
    async def send_to_admin(self, message: str) -> None:
        raise NotImplementedError("Linq not implemented in V1")

    async def send_to_phone(self, phone: str, message: str) -> None:
        raise NotImplementedError("Linq not implemented in V1")
