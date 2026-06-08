import json
import os
import re
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
######################################################################
#########################   Read this first   #########################
# Note for reusing the script:
# 1) When you search for SPCs on MHRA portal, it creates an API call that returns JSON with blob URLs.
#Search for a term, Go to Developer tools (F12) -> Network tab -> docs? - this is the API call. Copy the call, paste it in a browser, dont change API-Key. Jist update "top-10" to "top-500"
# Press enter and you will get a JSON. Download the JSON and use that as input to this script.
#  The link cretaed internally looks like: https://mhraproducts4853.search.windows.net/indexes/products-index/docs?api-key=17CCFC430C1A78A169B392A35A99C49D&api-version=2017-11-11&highlight=content&queryType=full&%24count=true&%24top=500&%24skip=20&search=%28Takeda~1+%7C%7C+UK%5E4%29&scoringProfile=preferKeywords&searchMode=all&%24filter=%28doc_type+eq+%27Spc%27%29
#  2) You need to get the API key from your browser's developer tools (network tab) when you make the search.
#  3) Change the value for "top" parameter to get more results per call (max 1000).
#  4) change the search query to your desired company name.
#  5) Save the JSON response to a local file and change the JSON_PATH variable below to point to that file.
############################################################################
############################################################################

JSON_PATH = r"C:\Users\anilp\OneDrive\Documents\tmp\response_00101.json"      # <-- change this to your local path
OUT_DIR = r"C:\Users\anilp\OneDrive\Documents\tmp\spc_pdfs"             # <-- output folder
MAX_DOWNLOADS = 500               # <-- how many SPCs you want
TIMEOUT = 60
SLEEP_BETWEEN = 0.35              # be polite


def iter_records_from_json(path: str) -> Iterable[Dict[str, Any]]:
    """
    Supports:
      1) Normal JSON: list[...] OR dict{ "value": [...] } OR dict{ "results": [...] }
      2) JSON Lines: one JSON object per line
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read().strip()

    # Try JSON first
    try:
        obj = json.loads(raw)
        if isinstance(obj, list):
            yield from obj
        elif isinstance(obj, dict):
            for key in ("value", "results", "documents", "data"):
                if key in obj and isinstance(obj[key], list):
                    yield from obj[key]
                    return
            # Fallback: might be a dict that is itself one record
            yield obj
        return
    except json.JSONDecodeError:
        pass

    # Fallback: JSON Lines
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if isinstance(rec, dict):
                    yield rec
            except json.JSONDecodeError:
                continue


def safe_filename(name: str) -> str:
    name = name.strip().replace("\u0000", "")
    # Windows-illegal characters
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:180] if len(name) > 180 else name


def choose_filename(rec: Dict[str, Any], url: str) -> str:
    # Prefer the provided PDF title if present
    title = rec.get("title") or rec.get("file_name") or ""
    title = safe_filename(str(title)) if title else ""

    if title and title.lower().endswith(".pdf"):
        return title

    # Otherwise derive from the blob id in the URL
    blob_id = url.rstrip("/").split("/")[-1]
    blob_id = safe_filename(blob_id)
    return f"{blob_id}.pdf"


def extract_download_targets(path: str) -> List[Tuple[str, str]]:
    """
    Returns list of (url, filename).
    Dedupes by URL.
    """
    seen = set()
    targets: List[Tuple[str, str]] = []

    for rec in iter_records_from_json(path):
        url = rec.get("metadata_storage_path") or rec.get("url") or rec.get("pdf_url")
        if not url or not isinstance(url, str):
            continue

        # If doc_type exists, keep only SPC
        doc_type = rec.get("doc_type")
        if doc_type and str(doc_type).lower() != "spc":
            continue

        url = url.strip()
        if url in seen:
            continue

        seen.add(url)
        filename = choose_filename(rec, url)
        targets.append((url, filename))

    return targets


def download_file(session: requests.Session, url: str, out_path: str) -> Tuple[bool, str]:
    try:
        with session.get(url, stream=True, timeout=TIMEOUT, allow_redirects=True) as r:
            if r.status_code != 200:
                return False, f"HTTP {r.status_code}"

            # Some blobs may not send content-type; we still save as .pdf
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
        return True, "OK"
    except requests.RequestException as e:
        return False, f"Request error: {e}"


def main():
    targets = extract_download_targets(JSON_PATH)
    if not targets:
        raise SystemExit("No download targets found in JSON. Check JSON_PATH / field names.")

    print(f"Found {len(targets)} unique SPC blob URLs in JSON.")
    targets = targets[:MAX_DOWNLOADS]
    print(f"Downloading first {len(targets)}...")

    session = requests.Session()
    # Optional: set a friendly user-agent
    session.headers.update({"User-Agent": "spc-downloader/1.0 (requests)"})

    ok = 0
    failed = 0

    for i, (url, filename) in enumerate(targets, start=1):
        out_path = os.path.join(OUT_DIR, filename)

        # Skip if already downloaded
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            print(f"[{i}/{len(targets)}] SKIP exists: {filename}")
            continue

        success, msg = download_file(session, url, out_path)
        if success:
            ok += 1
            print(f"[{i}/{len(targets)}] OK   {filename}")
        else:
            failed += 1
            print(f"[{i}/{len(targets)}] FAIL {filename}  ({msg})")

        time.sleep(SLEEP_BETWEEN)

    print(f"\nDone. Downloaded: {ok}, Failed: {failed}")
    if failed:
        print("If you see lots of HTTP 403, the blob container is not public; you’ll need MHRA-provided SAS links or an API route that returns signed URLs.")


if __name__ == "__main__":
    main()
