from models import format_ms


def test_format_ms():
    assert format_ms(83_467) == "1:23.467"
    assert format_ms(140_005) == "2:20.005"
    assert format_ms(59_999) == "0:59.999"
    assert format_ms(600_000) == "10:00.000"


def test_format_ms_degenerate():
    assert format_ms(None) == "–"
    assert format_ms(0) == "–"
    assert format_ms(-5) == "–"
