"""Decode the __NUXT_DATA__ payload that Nuxt 3 pages embed (devalue format)."""

from __future__ import annotations

import json
import re
from typing import Any

_SCRIPT = re.compile(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', re.S)
_WRAPPERS = {"Reactive", "ShallowReactive", "Ref", "ShallowRef"}
_EMPTY = {"EmptyRef", "EmptyShallowRef", "NuxtError", "Island"}


def extract_nuxt_data(html: str) -> Any:
    """Return the decoded Nuxt payload, or None if the page has none."""
    match = _SCRIPT.search(html)
    if not match:
        return None
    return unflatten(json.loads(match.group(1)))


def unflatten(arr: list) -> Any:
    """Rebuild the object graph from devalue's flat array of index references."""
    cache: dict[int, Any] = {}

    def hydrate(ref: Any) -> Any:
        if not isinstance(ref, int) or isinstance(ref, bool):
            return ref
        if ref < 0:
            return None
        if ref in cache:
            return cache[ref]
        value = arr[ref]
        if isinstance(value, list):
            if value and isinstance(value[0], str):
                tag = value[0]
                if tag in _WRAPPERS:
                    result = hydrate(value[1]) if len(value) > 1 else None
                    cache[ref] = result
                    return result
                if tag in _EMPTY:
                    cache[ref] = None
                    return None
                if tag == "Date":
                    cache[ref] = value[1]
                    return value[1]
                if tag == "Set":
                    out: list = []
                    cache[ref] = out
                    out.extend(hydrate(x) for x in value[1:])
                    return out
                if tag == "Map":
                    out_map: dict = {}
                    cache[ref] = out_map
                    for i in range(1, len(value) - 1, 2):
                        out_map[str(hydrate(value[i]))] = hydrate(value[i + 1])
                    return out_map
            out_list: list = []
            cache[ref] = out_list
            out_list.extend(hydrate(x) for x in value)
            return out_list
        if isinstance(value, dict):
            out_dict: dict = {}
            cache[ref] = out_dict
            for key, item in value.items():
                out_dict[key] = hydrate(item)
            return out_dict
        cache[ref] = value
        return value

    return hydrate(0)


def find_product_lists(payload: Any) -> list[list[dict]]:
    """Find every {'products': [...]} block in the payload's data section."""
    found: list[list[dict]] = []
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return found
    for block in data.values():
        if isinstance(block, dict) and isinstance(block.get("products"), list):
            found.append([p for p in block["products"] if isinstance(p, dict)])
    return found
