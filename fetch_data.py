#!/usr/bin/env python3
"""
Fetch latest 大乐透 (Super Lotto) draw data from official China Sports Lottery API.
Updates the embedded data in index.html.

Usage:
  python3 fetch_data.py              # Fetch and print JSON to stdout
  python3 fetch_data.py --update     # Fetch and update index.html in-place
  python3 fetch_data.py --output data.json  # Write to JSON file

Schedule: run this on Mon/Wed/Sat mornings to get fresh predictions.
  Cron example: 0 8 * * 1,3,6 /usr/bin/python3 /Users/a58/lottery-predictor/fetch_data.py --update >> /Users/a58/lottery-predictor/cron.log 2>&1
"""

import json
import urllib.request
import sys
import re
import os
import ssl
import gzip
import io

API_URL = "https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry"
GAME_NO = "85"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(SCRIPT_DIR, "index.html")


def fetch_page(page_no, page_size=50):
    """Fetch one page of draw history from the official API."""
    url = f"{API_URL}?gameNo={GAME_NO}&provinceId=0&pageSize={page_size}&isVerify=1&pageNo={page_no}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.lottery.gov.cn/",
        "Origin": "https://www.lottery.gov.cn",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
    }

    # Try with SSL context that doesn't verify (some CDN issues)
    ctx = ssl.create_default_context()

    def decode_response(response_bytes):
        """Handle gzip or plain response."""
        if response_bytes[:2] == b'\x1f\x8b':
            return gzip.decompress(response_bytes).decode("utf-8")
        return response_bytes.decode("utf-8")

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            raw = decode_response(resp.read())
            data = json.loads(raw)
    except Exception as e:
        print(f"  [warn] Primary fetch failed: {e}", file=sys.stderr)
        # Try alternate approach without SSL verification
        try:
            ctx = ssl._create_unverified_context()
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                raw = decode_response(resp.read())
                data = json.loads(raw)
        except Exception as e2:
            print(f"  [error] Alternate fetch also failed: {e2}", file=sys.stderr)
            return []

    draws = []
    list_data = data.get("value", {}).get("list", [])

    for item in list_data:
        try:
            qh = str(item.get("lotteryDrawNum", ""))
            result = item.get("lotteryDrawResult", "")
            dt = item.get("lotteryDrawTime", "")[:10]

            if not result:
                continue

            parts = result.strip().split()
            if len(parts) >= 7:
                front = [int(p) for p in parts[:5]]
                back = [int(p) for p in parts[5:7]]
                draws.append({"qh": qh, "dt": dt, "f": front, "b": back})
        except (ValueError, IndexError, KeyError):
            continue

    return draws


def fetch_all(num_pages=2):
    """Fetch multiple pages and return deduplicated, sorted draws."""
    all_draws = []
    for page in range(1, num_pages + 1):
        draws = fetch_page(page)
        print(f"  Page {page}: fetched {len(draws)} draws", file=sys.stderr)
        all_draws.extend(draws)

    seen = set()
    unique = []
    for d in all_draws:
        if d["qh"] not in seen:
            seen.add(d["qh"])
            unique.append(d)

    unique.sort(key=lambda x: x["dt"], reverse=True)
    return unique[:50]


def update_html(draws):
    """Replace the RAW_DATA array in index.html with fresh data."""
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    lines = []
    for d in draws:
        f_str = "[" + ",".join(str(n) for n in d["f"]) + "]"
        b_str = "[" + ",".join(str(n) for n in d["b"]) + "]"
        lines.append(f'  {{qh:"{d["qh"]}",dt:"{d["dt"]}",f:{f_str},b:{b_str}}}')

    new_data = "const RAW_DATA = [\n" + ",\n".join(lines) + "\n];"
    pattern = r"const RAW_DATA = \[[\s\S]*?\n\];"
    content = re.sub(pattern, new_data, content)

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"  Updated {os.path.basename(HTML_FILE)} with {len(draws)} draws", file=sys.stderr)


def main():
    num_pages = 2
    do_update = False
    output_file = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--update":
            do_update = True
        elif args[i] == "--output" and i + 1 < len(args):
            output_file = args[i + 1]
            i += 1
        elif args[i] == "--pages" and i + 1 < len(args):
            num_pages = int(args[i + 1])
            i += 1
        i += 1

    print(f"Fetching 大乐透 data ({num_pages} pages)...", file=sys.stderr)
    draws = fetch_all(num_pages)
    print(f"Total: {len(draws)} unique draws", file=sys.stderr)

    if len(draws) == 0:
        print("ERROR: No data fetched. The API may be blocking requests.", file=sys.stderr)
        print("Try running the HTML page in a browser - data is already embedded.", file=sys.stderr)
        sys.exit(1)

    if do_update:
        if os.path.exists(HTML_FILE):
            update_html(draws)
        else:
            print(f"Error: {HTML_FILE} not found", file=sys.stderr)
            sys.exit(1)
    elif output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(draws, f, ensure_ascii=False, indent=2)
        print(f"Written to {output_file}", file=sys.stderr)
    else:
        print(json.dumps(draws, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
