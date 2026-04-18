from models.orm import Client, Provider


def build_client_profile(client: Client) -> str:
    parts = [
        f"Name: {client.name}",
        f"Status: {client.status}",
    ]
    if client.membership_type:
        sessions = f" ({client.sessions_per_week}x/week)" if client.sessions_per_week else ""
        parts.append(f"Membership: {client.membership_type}{sessions}")
    if client.preferred_days:
        days = ", ".join(client.preferred_days)
        time_pref = f" {client.preferred_time}" if client.preferred_time else ""
        parts.append(f"Preferred: {days}{time_pref}")
    if client.address:
        parts.append(f"Address: {client.address}")
    if client.notes:
        parts.append(f"Notes: {client.notes}")
    return " | ".join(parts)


def build_provider_profile(provider: Provider) -> str:
    config = provider.business_config or {}
    parts = [
        f"Name: {provider.name}",
        f"Business: {provider.business_type}",
        f"Location: {provider.location_type}",
        f"Buffer: {provider.buffer_mins}min between sessions",
    ]
    if config.get("services"):
        parts.append(f"Services: {config['services']}")
    if config.get("pricing"):
        parts.append(f"Pricing: {config['pricing']}")
    return " | ".join(parts)
