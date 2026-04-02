"""Tests for nostrax.validation."""

from nostrax.validation import (
    validate_header_value,
    validate_positive_int,
    validate_proxy_url,
    validate_target_url,
)


def test_valid_target_url():
    assert validate_target_url("https://example.com") is None
    assert validate_target_url("http://example.com/page") is None


def test_rejects_file_scheme():
    err = validate_target_url("file:///etc/passwd")
    assert err is not None
    assert "scheme" in err.lower()


def test_rejects_ftp_scheme():
    err = validate_target_url("ftp://example.com")
    assert err is not None


def test_rejects_localhost():
    err = validate_target_url("http://localhost/admin")
    assert err is not None
    assert "localhost" in err.lower()


def test_rejects_loopback_ip():
    err = validate_target_url("http://127.0.0.1/admin")
    assert err is not None


def test_rejects_private_ip():
    err = validate_target_url("http://192.168.1.1")
    assert err is not None
    assert "private" in err.lower() or "Private" in err


def test_rejects_cloud_metadata():
    err = validate_target_url("http://169.254.169.254/latest/meta-data/")
    assert err is not None


def test_rejects_no_hostname():
    err = validate_target_url("http://")
    assert err is not None


def test_valid_proxy():
    assert validate_proxy_url("http://proxy:8080") is None
    assert validate_proxy_url("https://proxy:8080") is None
    assert validate_proxy_url("socks5://proxy:1080") is None


def test_rejects_invalid_proxy_scheme():
    err = validate_proxy_url("ftp://proxy:21")
    assert err is not None


def test_rejects_proxy_no_hostname():
    err = validate_proxy_url("http://")
    assert err is not None


def test_positive_int():
    assert validate_positive_int(0, "depth") is None
    assert validate_positive_int(10, "depth") is None
    err = validate_positive_int(-1, "depth")
    assert err is not None


def test_header_value_valid():
    assert validate_header_value("nostrax/1.0", "User-Agent") is None


def test_header_value_rejects_newline():
    err = validate_header_value("bad\r\nheader", "User-Agent")
    assert err is not None


def test_header_value_rejects_too_long():
    err = validate_header_value("x" * 501, "User-Agent")
    assert err is not None
