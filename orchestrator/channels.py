from datetime import datetime
from models.schemas import MessageEnvelope

# Channel key templates — format with .format(phone=...) where needed
CHAN_CLIENT_MSG = "msg:client:{phone}"
CHAN_ADMIN_MSG = "msg:admin"
CHAN_AGENT_EVENT = "event:agent:{phone}"
CHAN_BROADCAST = "event:broadcast"
CHAN_ORCHESTRATOR = "event:orchestrator"

STATE_CONVERSATION = "state:conversation:{phone}"
STATE_AGENT_REGISTRY = "state:agent:registry"
STATE_SESSION = "state:session:{phone}"
STATE_LAST_DONNA = "state:last_donna:{phone}"
STATE_TIMEOUT = "state:timeout:{phone}"


def make_envelope(event: str, phone: str, payload: dict, source: str) -> dict:
    return MessageEnvelope(
        event=event,
        phone=phone,
        payload=payload,
        timestamp=datetime.utcnow().isoformat(),
        source=source,
    ).model_dump()
