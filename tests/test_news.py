"""The RSS feed: titles and first paragraphs only, the links dropped."""
from datasources.news import NewsFeed, headlines, preview

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>US news</title>
<item><title>\xe2\x80\x98Quoted\xe2\x80\x99: first story</title>
<link>https://example.com/1</link>
<description>&lt;p&gt;The standfirst &amp;amp; nothing more&lt;/p&gt;&lt;p&gt;The article's first paragraph.&lt;/p&gt; &lt;a href="https://example.com/1"&gt;Continue reading...&lt;/a&gt;</description></item>
<item><title>Second story</title><description>No paragraphs, &lt;a href="x"&gt;Continue reading...&lt;/a&gt;</description></item>
<item><title>  </title><description>untitled: skipped</description></item>
<item><title>Third story</title></item>
<item><title>Fourth story</title><description>&lt;p&gt;Not shown&lt;/p&gt;</description></item>
</channel></rss>"""


def test_titles_and_standfirsts_only():
    items = headlines(RSS)
    assert [i["title"] for i in items] == ["\u2018Quoted\u2019: first story", "Second story", "Third story"]
    assert items[0]["preview"] == "The standfirst & nothing more"       # not the article, not the link
    assert items[1]["preview"] == "No paragraphs,"
    assert items[2]["preview"] == ""
    assert all(set(i) == {"title", "preview"} for i in items)            # no links kept
    assert len(headlines(RSS, count=5)) == 4


def test_preview_nested_markup():
    assert preview("<p>A <strong>bold</strong> <a href='x'>claim</a></p><p>more</p>") == "A bold claim"


class Response:
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_feed_polls_rss():
    seen = []

    def opener(req, timeout):
        seen.append(req.get_header("Accept"))
        return Response(RSS)
    feed = NewsFeed("news", "https://example.com/rss", 900, opener=opener, count=2)
    assert feed.poll() and len(feed.data) == 2 and "xml" in seen[0]

    def broken(req, timeout):
        return Response(b"<html>not a feed")
    feed.opener = broken
    assert not feed.poll() and len(feed.data) == 2                        # the last answer stays
