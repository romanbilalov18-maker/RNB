from datetime import datetime

def quote_age_seconds(quote_time: datetime, now: datetime) -> float:
    """Compute age with timezone normalization."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if quote_time.tzinfo is None or quote_time.utcoffset() is None:
        quote_time = quote_time.replace(tzinfo=now.tzinfo)
    return (now - quote_time.astimezone(now.tzinfo)).total_seconds()

def is_fresh_quote(quote_time: datetime | None, now: datetime, max_age_seconds: float) -> bool:
    if quote_time is None or max_age_seconds <= 0:
        return False
    age = quote_age_seconds(quote_time, now)
    return age <= max_age_seconds and age >= -60
