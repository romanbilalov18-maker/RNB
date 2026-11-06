import pytest
from bot.net_profit_guard import assess_net_profit

def test_net_return_passes_after_costs():
    result = assess_net_profit(expected_gross_return=.02, commission_rate=.0005,
        spread_pct=.002, slippage_bps=5, minimum_net_return=.01)
    assert result.allowed
    assert result.expected_net_return == pytest.approx(.015)

def test_costs_block_profitable_gross_signal():
    result = assess_net_profit(expected_gross_return=.003, commission_rate=.001,
        spread_pct=.002, slippage_bps=10, minimum_net_return=0)
    assert not result.allowed
    assert result.reason == "net_return_below_threshold"

@pytest.mark.parametrize("field,value", [
    ("expected_gross_return", float("nan")), ("commission_rate", -.1),
    ("spread_pct", 1.1), ("slippage_bps", -1), ("minimum_net_return", True)])
def test_invalid_inputs_fail_closed(field, value):
    args = dict(expected_gross_return=.01, commission_rate=.001,
        spread_pct=.001, slippage_bps=5, minimum_net_return=0)
    args[field] = value
    with pytest.raises(ValueError):
        assess_net_profit(**args)
