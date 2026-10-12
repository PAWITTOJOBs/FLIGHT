#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

HISTORY_URL = "https://aip.caat.or.th/"
OUT_ROOT = Path("data/aip-thailand/current")
CHECK_FILE = Path("data/aip-thailand/last-check.json")

PAGES = [
    "VT-cover-en-GB.html",
    "eAIP/VT-AD-1.3-en-GB.html",
    "eAIP/VT-ENR-2.1-en-GB.html",
    "eAIP/VT-ENR-3.1-en-GB.html",
    "eAIP/VT-ENR-3.2-en-GB.html",
    "eAIP/VT-ENR-3.3-en-GB.html",
    "eAIP/VT-ENR-3.4-en-GB.html",
    "eAIP/VT-ENR-3.5-en-GB.html",
    "eAIP/VT-ENR-4.1-en-GB.html",
    "eAIP/VT-ENR-4.4-en-GB.html",
    "eAIP/VT-ENR-5.1-en-GB.html",
    "eAIP/VT-ENR-5.2-en-GB.html",
]

HEADERS = {
    "User-Agent": "FlightPlanner-AIP-Updater/1.0 (+GitHub Actions)",
    "Accept-Language": "en-GB,en;q=0.9",
}

session = requests.Session()
session.headers.update(HEADERS)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == data:
        return False
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return True


def write_json_if_changed(path: Path, obj: dict) -> bool:
    raw = (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return atomic_write(path, raw)


def find_section_table(soup: BeautifulSoup, heading_text: str):
    for tag in soup.find_all(re.compile(r"^h[1-6]$")):
        if heading_text.lower() in clean_text(tag.get_text(" ", strip=True)).lower():
            table = tag.find_next("table")
            if table:
                return table
    return None


def parse_issue_row(table):
    if table is None:
        return None
    for tr in table.find_all("tr"):
        cells = [clean_text(x.get_text(" ", strip=True)) for x in tr.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        if re.fullmatch(r"\d{2}\s+[A-Z]{3}\s+\d{4}", cells[0].upper()):
            a = tr.find("a", href=True)
            return {
                "effective_date": cells[0],
                "publication_date": cells[1] if len(cells) > 1 else "",
                "description": cells[2] if len(cells) > 2 else "",
                "download_url": urljoin(HISTORY_URL, a["href"]) if a else "",
            }
    return None


def discover_current_issue():
    r = session.get(HISTORY_URL, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    current = parse_issue_row(find_section_table(soup, "Currently Effective Issue"))
    nxt = parse_issue_row(find_section_table(soup, "Next Issues"))
    if not current:
        raise RuntimeError("Could not identify CAAT Currently Effective Issue.")

    dt = datetime.strptime(current["effective_date"].upper(), "%d %b %Y")
    issue_slug = dt.strftime("%Y-%m-%d") + "-AIRAC"
    issue_root = f"https://aip.caat.or.th/{issue_slug}/html/"
    current["issue_slug"] = issue_slug
    current["issue_root"] = issue_root
    return current, nxt


def download_page(issue_root: str, rel_path: str):
    url = urljoin(issue_root, rel_path)
    r = session.get(url, timeout=45)
    if r.status_code == 404:
        return {"path": rel_path, "url": url, "status": "missing", "http_status": 404}, False
    r.raise_for_status()
    data = r.content
    target = OUT_ROOT / "html" / rel_path
    changed = atomic_write(target, data)
    return {
        "path": rel_path,
        "url": url,
        "status": "ok",
        "http_status": r.status_code,
        "bytes": len(data),
        "sha256": sha256_bytes(data),
    }, changed


def main():
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    current, next_issue = discover_current_issue()
    print("Current AIP:", current["effective_date"], current["issue_root"])

    page_results = []
    changed_count = 0

    for rel in PAGES:
        try:
            result, changed = download_page(current["issue_root"], rel)
            page_results.append(result)
            changed_count += int(changed)
            print(f'{result["status"]:>7}  {rel}')
        except Exception as exc:
            page_results.append({
                "path": rel,
                "url": urljoin(current["issue_root"], rel),
                "status": "error",
                "error": str(exc),
            })
            print(f"  error  {rel}: {exc}", file=sys.stderr)

    metadata = {
        "source": "Civil Aviation Authority of Thailand (CAAT) eAIP",
        "history_url": HISTORY_URL,
        "effective_date": current["effective_date"],
        "publication_date": current["publication_date"],
        "description": current["description"],
        "issue_slug": current["issue_slug"],
        "issue_root": current["issue_root"],
        "download_url": current["download_url"],
        "next_issue": next_issue,
        "pages": page_results,
    }
    if write_json_if_changed(OUT_ROOT / "metadata.json", metadata):
        changed_count += 1

    if changed_count:
        write_json_if_changed(CHECK_FILE, {
            "checked_at_utc": now,
            "currently_effective": current["effective_date"],
            "issue_root": current["issue_root"],
            "errors": [x for x in page_results if x["status"] == "error"],
            "missing": [x["path"] for x in page_results if x["status"] == "missing"],
        })

    print(f"Changed files/content groups: {changed_count}")
    print("Done.")


if __name__ == "__main__":
    main()
