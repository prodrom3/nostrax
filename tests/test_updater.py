"""Tests for nostrax.updater."""

from unittest.mock import patch

from nostrax.updater import check_update, get_latest_version, parse_version


def test_parse_version():
    assert parse_version("1.0.0") == (1, 0, 0)
    assert parse_version("2.10.3") == (2, 10, 3)
    assert parse_version("0.1.0") < parse_version("1.0.0")
    assert parse_version("1.0.0") == parse_version("1.0.0")
    assert parse_version("1.0.1") > parse_version("1.0.0")


@patch("nostrax.updater.urlopen")
def test_get_latest_version_success(mock_urlopen):
    mock_resp = mock_urlopen.return_value.__enter__.return_value
    mock_resp.read.return_value = b'{"info": {"version": "2.0.0"}}'

    result = get_latest_version()
    assert result == "2.0.0"


@patch("nostrax.updater.urlopen")
def test_get_latest_version_failure(mock_urlopen):
    from urllib.error import URLError

    mock_urlopen.side_effect = URLError("no internet")
    result = get_latest_version()
    assert result is None


@patch("nostrax.updater.get_latest_version")
@patch("nostrax.updater.__version__", "1.0.0")
def test_check_update_newer_available(mock_get):
    mock_get.return_value = "2.0.0"
    result = check_update()
    assert "2.0.0" in result
    assert "available" in result
    assert "pip install --upgrade" in result


@patch("nostrax.updater.get_latest_version")
@patch("nostrax.updater.__version__", "1.0.0")
def test_check_update_up_to_date(mock_get):
    mock_get.return_value = "1.0.0"
    result = check_update()
    assert "up to date" in result


@patch("nostrax.updater.get_latest_version")
@patch("nostrax.updater.__version__", "2.0.0")
def test_check_update_ahead_of_pypi(mock_get):
    mock_get.return_value = "1.0.0"
    result = check_update()
    assert "newer than PyPI" in result


@patch("nostrax.updater.get_latest_version")
def test_check_update_pypi_unreachable(mock_get):
    mock_get.return_value = None
    result = check_update()
    assert "Could not reach PyPI" in result
