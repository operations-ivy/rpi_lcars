"""Headlines for the status screen: an RSS feed (the Guardian's US edition by
default), polled like the homelab's feeds. Only each item's title is kept:
no links, no descriptions, never the article."""
import re
import xml.etree.ElementTree as ET
from html import unescape

from datasources.feeds import JsonFeed


def tidy(text):
    return re.sub(r"\s+", " ", unescape(text or "")).strip()


def headlines(body, count=3):
    """[{"title"}] for the feed's first count items."""
    items = ET.fromstring(body).findall("channel/item")
    out = []
    for item in items:
        title = tidy(item.findtext("title"))
        if title:
            out.append({"title": title})
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
