from datetime import date, datetime, time, timedelta


def parse_date(date_str: str) -> date:
    today = datetime.utcnow().date()
    lower = date_str.lower().strip()
    if lower in ("today", ""):
        return today
    if lower == "tomorrow":
        return today + timedelta(days=1)
    day_map = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
    }
    for day_name, day_num in day_map.items():
        if day_name in lower:
            days_ahead = (day_num - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return today + timedelta(days=days_ahead)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%B %d", "%b %d",
                "%B %d, %Y", "%b %d, %Y"):
        try:
            parsed = datetime.strptime(date_str, fmt)
            if parsed.year == 1900:
                parsed = parsed.replace(year=today.year)
            return parsed.date()
        except ValueError:
            continue
    return today


def parse_time(time_str: str) -> time:
    time_str = time_str.strip().upper()
    word_map = {
        "morning": "09:00 AM",
        "afternoon": "02:00 PM",
        "evening": "06:00 PM",
        "night": "07:00 PM",
    }
    for word, replacement in word_map.items():
        if word in time_str.lower():
            time_str = replacement
            break
    for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M", "%I %p", "%I%p"):
        try:
            return datetime.strptime(time_str, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse time: {time_str}")


def parse_datetime(date_str: str, time_str: str) -> datetime:
    d = parse_date(date_str)
    t = parse_time(time_str)
    return datetime.combine(d, t)


def looks_like_phone(text: str) -> bool:
    cleaned = (
        text.strip()
        .replace(" ", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
    )
    return (cleaned.startswith("+") or cleaned.isdigit()) and len(cleaned) >= 7
