"""Download raw law datasets from the MOJ Open API."""

import io
import json
import zipfile

import truststore

truststore.inject_into_ssl()

import requests

BASE_URL = "https://law.moj.gov.tw/api"

LANGS = ("zh", "en")
CATEGORIES = ("law", "order")

_LANG_PATH = {"zh": "Ch", "en": "En"}
_CATEGORY_PATH = {"law": "Law", "order": "Order"}


def fetch_dataset(category: str, lang: str, timeout: int = 120) -> dict:
    """Return the decoded dataset for one (category, lang) pair.

    The endpoint serves a zip archive; the payload is the single .json member.
    """
    if lang not in LANGS:
        raise ValueError(f"lang must be one of {LANGS}, got {lang!r}")
    if category not in CATEGORIES:
        raise ValueError(f"category must be one of {CATEGORIES}, got {category!r}")

    url = f"{BASE_URL}/{_LANG_PATH[lang]}/{_CATEGORY_PATH[category]}/JSON"
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".json"))
        with zf.open(name) as fh:
            # The MOJ files carry a UTF-8 BOM.
            return json.loads(fh.read().decode("utf-8-sig"))
