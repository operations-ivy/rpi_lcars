"""Headlines for the status screen: an RSS feed (the Guardian's US edition by
default), polled like the homelab's feeds. Only each item's title and its
first paragraph (the standfirst) are kept: no links, and never the article."""
import re
import xml.etree.ElementTree as ET
from html import unescape
from html.parser import HTMLParser

from datasources.feeds import JsonFeed


class _FirstParagraph(HTMLParser):
    """The text of the first <p>, or of everything outside links when there's
    no <p> (the Guardian's descriptions end with a "Continue reading..." link)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.first, self.loose, self.depth, self.in_link, self.done = [], [], 0, 0, False

    def handle_starttag(self, tag, attrs):
        if tag == "p" and not self.done:
            self.depth += 1
        elif tag == "a":
            self.in_link += 1

    def handle_endtag(self, tag):
        if tag == "p" and self.depth:
            self.depth -= 1
            self.done = self.done or (self.depth == 0 and bool(self.first))
        elif tag == "a" and self.in_link:
            self.in_link -= 1

    def handle_data(self, data):
        if self.depth and not self.done:
            self.first.append(data)
        elif not self.in_link and not self.done:
            self.loose.append(data)


def tidy(text):
    return re.sub(r"\s+", " ", unescape(text or "")).strip()


def preview(description):
    parser = _FirstParagraph()
    parser.feed(description or "")
    parser.close()
    return tidy("".join(parser.first or parser.loose))


def headlines(body, count=3):
    """[{"title", "preview"}] for the feed's first count items."""
    items = ET.fromstring(body).findall("channel/item")
    out = []
    for item in items:
        title = tidy(item.findtext("title"))
        if title:
            out.append({"title": title, "preview": preview(item.findtext("description"))})
        if len(out) == count:
            break
    return out


class NewsFeed(JsonFeed):
    accept = "application/rss+xml, application/xml, text/xml"

    def __init__(self, name, url, poll_seconds, metrics=None, count=3, **kwargs):
        super().__init__(name, url, poll_seconds, metrics, **kwargs)
        self.count = count

    def parse(self, body):
        return headlines(body, self.count)
