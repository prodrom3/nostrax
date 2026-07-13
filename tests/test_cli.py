"""Tests for nostrax.cli."""

import io
import pytest
from unittest.mock import patch, AsyncMock

from nostrax.cli import main, _parse_auth, _read_seeds


def test_read_seeds_from_file_skips_blanks_and_comments(tmp_path):
    p = tmp_path / "seeds.txt"
    p.write_text(
        "https://a.test\n\n# a comment\n  https://b.test  \nhttps://c.test\n",
        encoding="utf-8",
    )
    assert _read_seeds(str(p)) == [
        "https://a.test",
        "https://b.test",
        "https://c.test",
    ]


def test_read_seeds_from_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("https://a.test\n# skip\nhttps://b.test\n"))
    assert _read_seeds("-") == ["https://a.test", "https://b.test"]


@patch("nostrax.cli.validate_target_url", return_value=None)
@patch("nostrax.cli.crawl_seeds_async", new_callable=AsyncMock)
def test_main_input_file_crawls_seeds(mock_seeds, _mock_valid, tmp_path, capsys):
    mock_seeds.return_value = ["https://a.test/1", "https://b.test/2"]
    seedfile = tmp_path / "seeds.txt"
    seedfile.write_text("https://a.test\nhttps://b.test\n", encoding="utf-8")

    exit_code = main(["--input-file", str(seedfile)])
    assert exit_code == 0
    # crawl_seeds_async was called with both seeds
    called_seeds = mock_seeds.call_args[0][0]
    assert called_seeds == ["https://a.test", "https://b.test"]
    out = capsys.readouterr().out
    assert "https://a.test/1" in out


@patch("nostrax.cli.validate_target_url", return_value=None)
def test_main_input_file_with_cache_dir_errors(_mock_valid, tmp_path):
    seedfile = tmp_path / "seeds.txt"
    seedfile.write_text("https://a.test\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["--input-file", str(seedfile), "--cache-dir", "cache"])


@patch("nostrax.cli.validate_target_url", return_value=None)
@patch("nostrax.cli.crawl_async", new_callable=AsyncMock)
def test_main_proxy_file_builds_pool(mock_crawl, _mock_valid, tmp_path):
    mock_crawl.return_value = ["https://example.com/x"]
    pf = tmp_path / "proxies.txt"
    pf.write_text("http://a:1\n# comment\nhttp://b:2\n", encoding="utf-8")

    rc = main(["-t", "https://example.com", "--proxy-file", str(pf)])
    assert rc == 0
    assert mock_crawl.call_args.kwargs["proxies"] == ["http://a:1", "http://b:2"]


@patch("nostrax.cli.validate_target_url", return_value=None)
@patch("nostrax.cli.crawl_async", new_callable=AsyncMock)
def test_main_auto_throttle_flags(mock_crawl, _mock_valid):
    mock_crawl.return_value = ["https://example.com/x"]
    rc = main(
        [
            "-t",
            "https://example.com",
            "--auto-throttle",
            "--auto-throttle-max-delay",
            "5",
        ]
    )
    assert rc == 0
    kwargs = mock_crawl.call_args.kwargs
    assert kwargs["auto_throttle"] is True
    assert kwargs["auto_throttle_max_delay"] == 5.0


@patch("nostrax.cli.crawl_async", new_callable=AsyncMock)
def test_main_basic(mock_crawl, capsys):
    mock_crawl.return_value = ["https://example.com/page1", "https://example.com/page2"]
    exit_code = main(["-t", "https://example.com"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "https://example.com/page1" in output
    assert "https://example.com/page2" in output


@patch("nostrax.cli.crawl_async", new_callable=AsyncMock)
def test_main_silent(mock_crawl, capsys):
    mock_crawl.return_value = ["https://example.com/page1"]
    exit_code = main(["-t", "https://example.com", "-s"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert output == ""


@patch("nostrax.cli.crawl_async", new_callable=AsyncMock)
def test_main_json_format(mock_crawl, capsys):
    mock_crawl.return_value = ["https://example.com/page1"]
    exit_code = main(["-t", "https://example.com", "-f", "json"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert '"https://example.com/page1"' in output


@patch("nostrax.cli.crawl_async", new_callable=AsyncMock)
def test_main_no_urls(mock_crawl):
    mock_crawl.return_value = []
    exit_code = main(["-t", "https://example.com"])
    assert exit_code == 1


@patch("nostrax.cli.crawl_async", new_callable=AsyncMock)
def test_main_catches_nostrax_error(mock_crawl):
    from nostrax.exceptions import FetchError

    mock_crawl.side_effect = FetchError("https://example.com", "unreachable")
    exit_code = main(["-t", "https://example.com"])
    assert exit_code == 1


@patch("nostrax.cli.crawl_async", new_callable=AsyncMock)
def test_main_returns_130_on_keyboard_interrupt(mock_crawl):
    mock_crawl.side_effect = KeyboardInterrupt()
    exit_code = main(["-t", "https://example.com"])
    assert exit_code == 130


@patch("nostrax.cli.crawl_async", new_callable=AsyncMock)
def test_main_sort(mock_crawl, capsys):
    mock_crawl.return_value = ["https://example.com/z", "https://example.com/a"]
    exit_code = main(["-t", "https://example.com", "--sort"])
    assert exit_code == 0
    output = capsys.readouterr().out
    lines = output.strip().split("\n")
    assert lines == sorted(lines)


@patch("nostrax.cli.crawl_async", new_callable=AsyncMock)
def test_main_domain_filter(mock_crawl, capsys):
    mock_crawl.return_value = ["https://example.com/local", "https://other.com/ext"]
    exit_code = main(["-t", "https://example.com", "--domain", "internal"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "https://example.com/local" in output
    assert "https://other.com/ext" not in output


@patch("nostrax.cli.crawl_async", new_callable=AsyncMock)
def test_main_passes_max_concurrent(mock_crawl):
    mock_crawl.return_value = ["https://example.com/page"]
    main(["-t", "https://example.com", "--max-concurrent", "5"])
    _, kwargs = mock_crawl.call_args
    assert kwargs["max_concurrent"] == 5


@patch("nostrax.cli.crawl_async", new_callable=AsyncMock)
def test_main_passes_respect_robots(mock_crawl):
    mock_crawl.return_value = ["https://example.com/page"]
    main(["-t", "https://example.com", "--respect-robots"])
    _, kwargs = mock_crawl.call_args
    assert kwargs["respect_robots"] is True


@patch("nostrax.cli.crawl_async", new_callable=AsyncMock)
def test_main_passes_max_urls(mock_crawl):
    mock_crawl.return_value = ["https://example.com/page"]
    main(["-t", "https://example.com", "--max-urls", "100"])
    _, kwargs = mock_crawl.call_args
    assert kwargs["max_urls"] == 100


@patch("nostrax.cli.crawl_async", new_callable=AsyncMock)
def test_main_passes_rate_limit(mock_crawl):
    mock_crawl.return_value = ["https://example.com/page"]
    main(["-t", "https://example.com", "--rate-limit", "0.5"])
    _, kwargs = mock_crawl.call_args
    assert kwargs["rate_limit"] == 0.5


@patch("nostrax.cli.crawl_async", new_callable=AsyncMock)
def test_main_passes_proxy(mock_crawl):
    mock_crawl.return_value = ["https://example.com/page"]
    main(["-t", "https://example.com", "--proxy", "http://proxy:8080"])
    _, kwargs = mock_crawl.call_args
    assert kwargs["proxy"] == "http://proxy:8080"


@patch("nostrax.cli.crawl_async", new_callable=AsyncMock)
def test_main_passes_auth(mock_crawl):
    mock_crawl.return_value = ["https://example.com/page"]
    main(["-t", "https://example.com", "--auth", "user:pass"])
    _, kwargs = mock_crawl.call_args
    assert kwargs["auth"] == ("user", "pass")


@patch("nostrax.cli.crawl_async", new_callable=AsyncMock)
def test_main_passes_sitemap(mock_crawl):
    mock_crawl.return_value = ["https://example.com/page"]
    main(["-t", "https://example.com", "--sitemap"])
    _, kwargs = mock_crawl.call_args
    assert kwargs["use_sitemap"] is True


@patch("nostrax.cli.crawl_async", new_callable=AsyncMock)
def test_main_exclude_filter(mock_crawl, capsys):
    mock_crawl.return_value = [
        "https://example.com/page",
        "https://example.com/image.jpg",
    ]
    exit_code = main(["-t", "https://example.com", "--exclude", r"\.jpg$"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "https://example.com/page" in output
    assert "image.jpg" not in output


def test_main_version(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["-V"])
    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "nostrax" in output


@patch("nostrax.updater.get_latest_version")
def test_main_check_update(mock_get, capsys):
    mock_get.return_value = "1.0.0"
    exit_code = main(["--check-update"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "nostrax" in output


def test_main_no_target_errors():
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code != 0


def test_parse_auth_with_password():
    assert _parse_auth("user:pass") == ("user", "pass")


def test_parse_auth_with_colon_in_password():
    assert _parse_auth("user:p:a:ss") == ("user", "p:a:ss")


def test_parse_auth_no_password():
    assert _parse_auth("user") == ("user", "")


@patch("nostrax.cli.crawl_async", new_callable=AsyncMock)
def test_main_passes_retries(mock_crawl):
    mock_crawl.return_value = ["https://example.com/page"]
    main(["-t", "https://example.com", "--retries", "5", "--no-config"])
    _, kwargs = mock_crawl.call_args
    assert kwargs["retries"] == 5


@patch("nostrax.cli.crawl_async", new_callable=AsyncMock)
def test_main_passes_scope(mock_crawl):
    mock_crawl.return_value = ["https://example.com/docs/page"]
    main(["-t", "https://example.com", "--scope", "/docs/", "--no-config"])
    _, kwargs = mock_crawl.call_args
    assert kwargs["scope"] == "/docs/"


@patch("nostrax.cli.crawl_async", new_callable=AsyncMock)
def test_main_passes_strategy(mock_crawl):
    mock_crawl.return_value = ["https://example.com/page"]
    main(["-t", "https://example.com", "--strategy", "bfs", "--no-config"])
    _, kwargs = mock_crawl.call_args
    assert kwargs["strategy"] == "bfs"


@patch("nostrax.cli.crawl_async", new_callable=AsyncMock)
def test_main_passes_cache_dir(mock_crawl, tmp_path):
    mock_crawl.return_value = ["https://example.com/page"]
    cache = str(tmp_path / "cache")
    main(["-t", "https://example.com", "--cache-dir", cache, "--no-config"])
    _, kwargs = mock_crawl.call_args
    assert kwargs["cache_dir"] == cache
