"""INTERSPAR: the weekly leaflet on flugblatt.interspar.at (an iPaper flip book) offers a PDF download.

The flip book lives at /{region}/{region}_kw{week}/ and 'GetPDF.ashx' answers with a
redirect to the PDF file. The PDF is read with pdf_layout like the BILLA leaflets.
"""

from __future__ import annotations

from datetime import date, timedelta

BASE = "https://flugblatt.interspar.at"
NO_OWN_LEAFLET = {"burgenland": "wien"}  # Burgenland gets the Vienna leaflet


def region_slug(region: str) -> str:
    slug = (
        region.lower()
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace(" ", "")
    )
    return NO_OWN_LEAFLET.get(slug, slug)


def flipbook_urls(region: str, today: date) -> list[str]:
    """This week's leaflet first, then last week's (a new one may not be online yet)."""
    slug = region_slug(region)
    urls = []
    for day in (today, today - timedelta(days=7)):
        week = day.isocalendar().week
        urls.append(f"{BASE}/{slug}/{slug}_kw{week}/")
    return urls


def pdf_endpoint(flipbook: str) -> str:
    return f"{flipbook}GetPDF.ashx"
