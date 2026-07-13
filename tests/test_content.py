"""Tests for nostrax.content."""

from nostrax.content import PageContent, extract_content

RICH_HTML = """
<html lang="en-GB">
<head>
  <title>  Widgets Inc  </title>
  <meta name="description" content="We sell widgets.">
  <meta name="keywords" content="widgets, gadgets">
  <meta name="robots" content="noindex, nofollow">
  <meta property="og:title" content="Widgets OG">
  <meta property="og:image" content="https://cdn.example/w.png">
  <link rel="canonical" href="/canonical-widgets">
  <script type="application/ld+json">{"@type": "Organization", "name": "Widgets Inc"}</script>
  <script type="application/ld+json">not valid json</script>
</head>
<body><p>hi</p></body>
</html>
"""


def test_extract_basic_fields():
    c = extract_content(RICH_HTML, "https://shop.example/x", depth=2)
    assert isinstance(c, PageContent)
    assert c.title == "Widgets Inc"  # trimmed
    assert c.description == "We sell widgets."
    assert c.keywords == "widgets, gadgets"
    assert c.robots == "noindex, nofollow"
    assert c.lang == "en-GB"
    assert c.depth == 2


def test_canonical_resolved_against_page_url():
    c = extract_content(RICH_HTML, "https://shop.example/deep/x")
    assert c.canonical == "https://shop.example/canonical-widgets"


def test_open_graph_collected():
    c = extract_content(RICH_HTML, "https://shop.example/x")
    assert c.og["og:title"] == "Widgets OG"
    assert c.og["og:image"] == "https://cdn.example/w.png"


def test_jsonld_parsed_and_bad_json_skipped():
    c = extract_content(RICH_HTML, "https://shop.example/x")
    # One valid block parsed, the invalid one dropped silently.
    assert len(c.jsonld) == 1
    assert c.jsonld[0]["name"] == "Widgets Inc"


def test_missing_fields_default_empty():
    c = extract_content("<html><body>nothing</body></html>", "https://x.test/")
    assert c.title == ""
    assert c.description == ""
    assert c.canonical == ""
    assert c.og == {}
    assert c.jsonld == []


def test_to_dict_omits_empty():
    c = extract_content("<html><head><title>T</title></head></html>", "https://x.test/")
    d = c.to_dict()
    assert d["url"] == "https://x.test/"
    assert d["title"] == "T"
    assert "description" not in d  # empty fields omitted
    assert "og" not in d
