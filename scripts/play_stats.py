#!/usr/bin/env python3
"""브리핑 코리아(com.political.app) Play 설치 통계 조회.

Play Console의 통계 벌크 리포트(Cloud Storage export)를 서비스 계정으로 읽어
설치 수 / 활성 기기 수를 요약한다. gcloud/gsutil 불필요 — GCS JSON API 직접 호출.

사전 준비(사용자, 콘솔 1회):
  1. Google Cloud Console → 서비스 계정 생성 → JSON 키 발급
  2. Play Console → 설정 → API 액세스 → 그 서비스 계정 연결/권한 부여
     (또는 Cloud Storage 버킷에 서비스 계정 objectViewer 권한)
  3. Play Console → 다운로드(Download reports) → 통계 화면의
     Cloud Storage URI(gs://pubsite_prod_rev_XXXX/) 확인

사용:
  ~/side/politics_backend/.venv/bin/python scripts/play_stats.py \
      --key ~/Downloads/play-sa.json \
      --bucket pubsite_prod_rev_0123456789 \
      [--month 202607]

--month 생략 시 최근 2개월을 시도한다.
"""
import argparse
import csv
import io
import sys
import urllib.parse
import urllib.request

import google.auth.transport.requests
from google.oauth2 import service_account

PACKAGE = "com.political.app"
SCOPE = "https://www.googleapis.com/auth/devstorage.read_only"
GCS = "https://storage.googleapis.com/storage/v1/b"


def token(key_path):
    creds = service_account.Credentials.from_service_account_file(
        key_path, scopes=[SCOPE]
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def _get(url, tok):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def list_objects(bucket, prefix, tok):
    url = f"{GCS}/{bucket}/o?prefix={urllib.parse.quote(prefix)}"
    import json

    data = json.loads(_get(url, tok).decode("utf-8"))
    return [o["name"] for o in data.get("items", [])]


def download(bucket, obj, tok):
    url = f"{GCS}/{bucket}/o/{urllib.parse.quote(obj, safe='')}?alt=media"
    return _get(url, tok)


def parse_installs_overview(raw):
    # Play 통계 CSV는 UTF-16LE(BOM) 인코딩.
    text = raw.decode("utf-16")
    rows = list(csv.DictReader(io.StringIO(text)))
    return rows


def summarize(rows):
    if not rows:
        print("  (데이터 행 없음)")
        return
    # 관심 컬럼 후보 (Play 리포트 헤더가 버전마다 조금씩 다름)
    def col(row, *names):
        for n in names:
            for k in row:
                if k.strip().lower() == n.lower():
                    return row[k]
        return None

    last = rows[-1]
    date = col(last, "Date")
    active = col(last, "Active Device Installs", "Active Devices")
    total_users = col(last, "Total User Installs")
    print(f"  최신일자: {date}")
    print(f"  활성 기기 설치수(Active Device Installs): {active}")
    print(f"  누적 사용자 설치수(Total User Installs):   {total_users}")
    # 최근 7일 일일 신규 설치
    daily = [col(r, "Daily Device Installs") for r in rows[-7:]]
    daily = [d for d in daily if d not in (None, "")]
    if daily:
        print(f"  최근 {len(daily)}일 일일 신규 설치: {', '.join(daily)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True, help="서비스 계정 JSON 키 경로")
    ap.add_argument("--bucket", required=True, help="gs:// 없이 버킷 이름 (pubsite_prod_rev_...)")
    ap.add_argument("--month", help="YYYYMM (생략 시 자동 탐색)")
    args = ap.parse_args()

    bucket = args.bucket.replace("gs://", "").strip("/")
    tok = token(args.key)

    prefix = "stats/installs/"
    print(f"버킷: {bucket}  패키지: {PACKAGE}\n")

    if args.month:
        candidates = [f"stats/installs/installs_{PACKAGE}_{args.month}_overview.csv"]
    else:
        # 버킷에서 이 패키지의 overview 파일들을 찾아 최신 것 사용
        objs = list_objects(bucket, prefix + f"installs_{PACKAGE}", tok)
        overview = sorted(o for o in objs if o.endswith("_overview.csv"))
        if not overview:
            print("overview CSV를 못 찾음. 버킷 내 stats/installs 목록:")
            for o in list_objects(bucket, prefix, tok)[:20]:
                print("  ", o)
            sys.exit(1)
        candidates = overview[-2:]  # 최근 2개월

    for obj in candidates:
        print(f"[{obj}]")
        try:
            raw = download(bucket, obj, tok)
            summarize(parse_installs_overview(raw))
        except urllib.error.HTTPError as e:
            print(f"  가져오기 실패: HTTP {e.code} — 권한/파일명 확인")
        print()


if __name__ == "__main__":
    main()
