"""Offer sources for BierAlarm.

Parsers take page content and return Deals, so they can be tested without
network access. Fetching is done by the coordinator with Home Assistant's
shared aiohttp session.
"""
