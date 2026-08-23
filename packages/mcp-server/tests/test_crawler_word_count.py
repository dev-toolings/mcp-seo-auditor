"""Word-count extraction in CrawlerService._parse_html.

Regression: React 19 / Next.js streaming (PPR/Suspense) emits an almost-empty
<main> while the real content lives in sibling <template> holders. The naive
`soup.find("main") or soup.find("body")` short-circuited on the empty <main>,
reporting word_count = 0 and flagging fully-SSR pages as thin content.
"""

from app.services.crawler_service import CrawledPage, CrawlerService


def _parse(html: str) -> CrawledPage:
    page = CrawledPage(url="https://example.test/", status_code=200)
    CrawlerService()._parse_html(page, html)
    return page


def test_classic_main_is_counted():
    """A normal <main> with content is counted directly."""
    html = """
    <html><body>
      <header>menu</header>
      <main><h1>Voiture occasion Aurillac</h1>
        <p>Acheter une voiture d'occasion a Aurillac dans le Cantal avec IAutos.</p>
      </main>
      <footer>liens</footer>
    </body></html>
    """
    page = _parse(html)
    assert page.word_count > 5
    assert "Aurillac" in page.content


def test_streaming_empty_main_falls_back_to_body():
    """Next streaming: <main> holds only scripts/templates, content is a sibling."""
    real_content = " ".join(["mot"] * 200)
    html = f"""
    <html><body>
      <header>menu global</header>
      <main><script>self.__next_f.push([1])</script>
        <template id="B:0"></template><template id="B:1"></template>
      </main>
      <section><h1>Voiture occasion Aurillac</h1><p>{real_content}</p></section>
      <footer>liens footer</footer>
    </body></html>
    """
    page = _parse(html)
    assert page.word_count >= 200, f"expected body fallback, got {page.word_count}"
    assert "mot" in page.content
    # noise stripped
    assert "menu global" not in page.content
    assert "liens footer" not in page.content


def test_genuinely_empty_page_stays_zero():
    """A page with no real text must still report ~0 words (no false content)."""
    html = "<html><body><main><script>x</script></main><footer>f</footer></body></html>"
    page = _parse(html)
    assert page.word_count < 50
