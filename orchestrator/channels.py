# Redis key templates, formatted with .format(phone=...) where needed
STATE_AGENT_REGISTRY = "state:agent:registry"
STATE_OPEN_REQUESTS = "state:open_requests"
STATE_SESSION = "state:session:{phone}"
STATE_LAST_DONNA = "state:last_donna:{phone}"
STATE_TIMEOUT = "state:timeout:{phone}"
