"""Tests for the power/AI-infrastructure sector module (pure logic, no network)."""

from investor_ai import power_sector


def test_watchlist_entries_have_required_fields():
    assert len(power_sector.POWER_SECTOR_WATCHLIST) > 0
    for entry in power_sector.POWER_SECTOR_WATCHLIST:
        assert entry["ticker"]
        assert entry["category"]
        assert isinstance(entry["gas_exposed"], bool)


def test_natural_gas_up_notable_is_pressure():
    direction, message = power_sector.score_natural_gas_trend(15.0)
    assert direction == "pressure"
    assert "up 15.0%" in message


def test_natural_gas_down_notable_is_tailwind():
    direction, message = power_sector.score_natural_gas_trend(-15.0)
    assert direction == "tailwind"
    assert "down 15.0%" in message


def test_natural_gas_small_move_is_neutral_with_no_message():
    direction, message = power_sector.score_natural_gas_trend(2.0)
    assert direction == "neutral"
    assert message is None


def test_natural_gas_missing_data_is_neutral_with_no_message():
    direction, message = power_sector.score_natural_gas_trend(None)
    assert direction == "neutral"
    assert message is None


def test_glossary_has_expected_terms():
    for term in ("merit_order", "heat_rate", "spark_spread", "capacity_vs_energy_only", "duck_curve"):
        assert term in power_sector.BOOK_GLOSSARY
        assert len(power_sector.BOOK_GLOSSARY[term]) > 0
