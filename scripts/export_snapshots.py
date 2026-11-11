"""공개 GET 응답을 정적 JSON으로 내보낸다(GitHub Pages 배포용, 표준 라이브러리만 사용).

- 갱신 대상이면 API를 호출해 정상 응답(200 + success)만 채택한다. 캐시 우회 파라미터를 붙여 방금 끝난 수집 결과를 받는다.
- 갱신 대상이 아니거나 API가 실패하면 현재 배포된 Pages 파일(last-known-good)을 그대로 다시 싣는다.
  → Firestore가 쿼터로 막혀도 앱은 마지막 정상 스냅샷을 계속 받는다.

실행: python scripts/export_snapshots.py --out _site
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.snapshot_plan import SNAPSHOTS, canonical_key, choose, is_due, valid_body  # noqa: E402

API_BASE = os.getenv("SNAPSHOT_API_BASE", "https://politicsbackend-ruby.vercel.app")
PAGES_BASE = os.getenv("SNAPSHOT_PAGES_BASE", "https://sjoongh.github.io/politics_backend")
UA = {"User-Agent": "BriefingKoreaSnapshot/1.0", "Accept": "application/json"}


def _get_json(url: str, timeout: int):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:  # noqa: BLE001 — 네트워크·파싱 오류는 '못 받음'으로 처리
        print(f"[snapshot] {url}: {e!r}")
        return 0, None


def run(out_dir: str) -> int:
    now = datetime.now(timezone.utc)
    os.makedirs(os.path.join(out_dir, "v1"), exist_ok=True)
    manifest = {"generated_at": now.isoformat(), "files": {}}
    written = 0
    for entry in SNAPSHOTS:
        key = canonical_key(entry["path"], entry["params"])
        _, prev = _get_json(f"{PAGES_BASE}/v1/{entry['file']}?t={int(time.time())}", timeout=15)
        fresh = None
        if is_due(entry, prev, now):
            params = dict(entry["params"], _snapshot=int(time.time()))  # CDN 캐시 키 우회(방금 수집분)
            status, body = _get_json(f"{API_BASE}{entry['path']}?{urlencode(params)}", timeout=60)
            if valid_body(status, body):
                fresh = body
            else:
                print(f"[snapshot] {key}: API status={status} success={(body or {}).get('success')} → 이전본 유지")
        doc = choose(entry, prev, fresh, now)
        if doc is None:
            print(f"[snapshot] {key}: 정상본 없음 → 파일 생략")
            continue
        with open(os.path.join(out_dir, "v1", entry["file"]), "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
        manifest["files"][entry["file"]] = {"request": doc["request"], "generated_at": doc["generated_at"],
                                            "refreshed": fresh is not None}
        written += 1
        print(f"[snapshot] {key}: {'refreshed' if fresh is not None else 'kept'} ({doc['generated_at']})")
    with open(os.path.join(out_dir, "v1", "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write("<!doctype html><meta charset=utf-8><title>BriefingKorea snapshots</title>"
                "<p>공개 데이터 스냅샷입니다. <a href=v1/manifest.json>manifest</a></p>")
    open(os.path.join(out_dir, ".nojekyll"), "w").close()
    print(f"[snapshot] files={written}/{len(SNAPSHOTS)}")
    return 0 if written else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="_site")
    sys.exit(run(ap.parse_args().out))
