ACTIVE_STATUSES = frozenset({
    "NORMAL_TRADING",
    "OPENING_PERIOD",
    "CLOSING_PERIOD",
    "SESSION_OPEN",
    "DEALER_NORMAL_TRADING",
    "SECURITY_TRADING_STATUS_NORMAL_TRADING",
    "SECURITY_TRADING_STATUS_OPENING_PERIOD",
    "SECURITY_TRADING_STATUS_CLOSING_PERIOD",
    "SECURITY_TRADING_STATUS_SESSION_OPEN",
    "SECURITY_TRADING_STATUS_DEALER_NORMAL_TRADING",
})


def is_instrument_active(status: object) -> bool:
    """Recognize explicit active T-Invest statuses; schedule remains a separate gate."""
    name = str(getattr(status, "name", status) or "").upper()
    return name in ACTIVE_STATUSES
