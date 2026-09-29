#!/usr/bin/env python3
import argparse
import csv
import hashlib
import sys
import time
from urllib.parse import urlparse
import requests

# Common non-sensitive parameters to probe for basic behavior differences
DEFAULT_PARAMS = [
    "id", "page", "q", "query", "search",
    "name", "user", "username", "category", "type",
    "sort", "order", "filter", "lang", "format",
    "view", "debug", "test", "ref", "source"
]


def check_local_target(url):
    """Make sure we only hit localhost or 127.0.0.1 for local lab practice."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL must start with http:// or https://")
    
    host = (parsed.hostname or "").lower()
    if host not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError(f"Safety restriction: target host '{host}' is not a local loopback address.")
    return url


def get_hash(content):
    return hashlib.sha256(content).hexdigest()


def detect_difference(base_resp, test_resp):
    diffs = []
    if test_resp.status_code != base_resp.status_code:
        diffs.append("status")
    if len(test_resp.content) != len(base_resp.content):
        diffs.append("size")
    if get_hash(test_resp.content) != get_hash(base_resp.content):
        diffs.append("body")
    return "+".join(diffs) if diffs else "no_change"


def run_discovery(target_url, output_file, timeout=5.0, delay=0.2):
    session = requests.Session()
    session.headers.update({"User-Agent": "ParamDiscovery/1.0"})

    print(f"Target URL : {target_url}")
    print("Fetching baseline response...")

    try:
        baseline = session.get(target_url, timeout=timeout, allow_redirects=False)
    except requests.RequestException as err:
        print(f"Error connecting to baseline target: {err}", file=sys.stderr)
        return 1

    base_len = len(baseline.content)
    base_hash = get_hash(baseline.content)
    print(f"Baseline -> Status: {baseline.status_code}, Size: {base_len} bytes, SHA256: {base_hash[:10]}...")

    results = []
    print(f"\nTesting {len(DEFAULT_PARAMS)} parameters...")

    for idx, param in enumerate(DEFAULT_PARAMS, 1):
        test_val = "test"
        row = {
            "parameter": param,
            "test_value": test_val,
            "baseline_status": baseline.status_code,
            "test_status": "",
            "baseline_size": base_len,
            "test_size": "",
            "size_delta": "",
            "baseline_sha256": base_hash,
            "test_sha256": "",
            "behavior": "",
            "url_tested": target_url,
            "error": ""
        }

        try:
            resp = session.get(target_url, params={param: test_val}, timeout=timeout, allow_redirects=False)
            curr_len = len(resp.content)
            curr_hash = get_hash(resp.content)
            behavior = detect_difference(baseline, resp)

            row["test_status"] = resp.status_code
            row["test_size"] = curr_len
            row["size_delta"] = curr_len - base_len
            row["test_sha256"] = curr_hash
            row["behavior"] = behavior

            flag = f"[{behavior}]" if behavior != "no_change" else ""
            print(f"  [{idx:02d}/{len(DEFAULT_PARAMS)}] ?{param}={test_val} -> status {resp.status_code}, len {curr_len} {flag}")

        except requests.RequestException as err:
            row["error"] = str(err)
            row["behavior"] = "request_error"
            print(f"  [{idx:02d}/{len(DEFAULT_PARAMS)}] ?{param}={test_val} -> failed ({err})")

        results.append(row)
        if delay > 0:
            time.sleep(delay)

    # Save findings
    fieldnames = [
        "parameter", "test_value", "baseline_status", "test_status",
        "baseline_size", "test_size", "size_delta", "baseline_sha256",
        "test_sha256", "behavior", "url_tested", "error"
    ]

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    notable = [r for r in results if r["behavior"] not in ("no_change", "request_error")]
    print(f"\nDone! Report saved to '{output_file}'.")
    print(f"Summary: {len(notable)}/{len(DEFAULT_PARAMS)} parameters triggered noticeable behavior changes.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Test local web applications for parameter response differences.")
    parser.add_argument("url", help="Target URL (e.g. http://127.0.0.1:5000/ or http://localhost:8000/)")
    parser.add_argument("-o", "--output", default="parameter_discovery_report.csv", help="Output CSV path (default: parameter_discovery_report.csv)")
    parser.add_argument("-t", "--timeout", type=float, default=5.0, help="Per-request timeout in seconds (default: 5.0)")
    parser.add_argument("-d", "--delay", type=float, default=0.1, help="Delay between requests in seconds (default: 0.1)")

    args = parser.parse_args()

    try:
        clean_url = check_local_target(args.url)
    except ValueError as e:
        print(f"Validation error: {e}", file=sys.stderr)
        sys.exit(1)

    sys.exit(run_discovery(clean_url, args.output, timeout=args.timeout, delay=args.delay))


if __name__ == "__main__":
    main()
