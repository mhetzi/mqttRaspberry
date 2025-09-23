
from typing import Any

def getDictWithContaining(d: dict, key=None, value=None, value_search_list=False) -> dict | None:
    if key is None and value is None:
        raise ValueError("key and value is none, cant search for dict")
    if d is None:
        raise ValueError("Searching in none dict is impossible")
    if key in d.keys():
        return d
    if value in d.values():
        return d
    for val in d.values():
        if isinstance(val, dict):
            res = getDictWithContaining(val, key, value)
            if res is not None: return res
        if value_search_list and isinstance(val, list) and value in val:
            return d
        if isinstance(val, list) and value_search_list:
            for v in val:
                if isinstance(v, dict):
                    res = getDictWithContaining(v, key, value, value_search_list=value_search_list)
                    if res is not None: return res
                try:
                    if value in v:
                        return d
                except TypeError:
                    if v == value:
                        return d
    return None