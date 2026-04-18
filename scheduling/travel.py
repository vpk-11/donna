from config import settings


async def get_travel_minutes(origin: str, destination: str) -> int:
    if not settings.google_maps_api_key:
        return 0

    import httpx
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origin,
        "destinations": destination,
        "mode": "driving",
        "key": settings.google_maps_api_key,
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        data = response.json()

    try:
        duration_seconds = data["rows"][0]["elements"][0]["duration"]["value"]
        return duration_seconds // 60
    except (KeyError, IndexError):
        return 0
