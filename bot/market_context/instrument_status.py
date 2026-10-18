ACTIVE_STATUSES = frozenset({"NORMAL_TRADING", "OPENING_PERIOD", "CLOSING_PERIOD", "SECURITY_TRADING_STATUS_NORMAL_TRADING", "SECURITY_TRADING_STATUS_OPENING_PERIOD", "SECURITY_TRADING_STATUS_CLOSING_PERIOD"})

def is_instrument_active(status: object) -> bool:
    name = str(getattr(status, "name", status) or "").upper()
    return name in ACTIVE_STATUSES
