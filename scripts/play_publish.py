#!/usr/bin/env python3
"""브리핑 코리아(com.political.app) AAB를 Play에 업로드하고 트랙에 출시.

Google Play Developer API(androidpublisher v3)로 AAB 업로드 → 지정 트랙 롤아웃 →
커밋까지 한 번에. Play Console UI에서 "출시 시작" 누르는 과정을 대체한다.

사전 준비(사용자, 콘솔 1회):
  1. Google Cloud Console → 해당 프로젝트에서 "Google Play Android Developer API" 사용 설정
  2. 서비스 계정 JSON 키 발급(통계용과 같은 계정 재사용 가능)
  3. Play Console → 사용자 및 권한 → 그 서비스 계정 이메일 초대 →
     앱 권한: "프로덕션 출시(Release to production)" + "앱 정보 편집" 부여
     (첫 프로덕션 릴리스는 API로 불가 — 이 앱은 이미 프로덕션 이력이 있어 가능)

사용:
  ~/side/politics_backend/.venv/bin/python scripts/play_publish.py \
      --key ~/Downloads/play-sa.json \
      --aab ~/side/politics_front/android/app/build/outputs/bundle/release/app-release.aab \
      [--track production] [--fraction 0.1] [--notes "Android 16 대응"]

--fraction 지정 시 단계적 출시(inProgress), 생략 시 100% 완료(completed).
"""
import argparse
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

PACKAGE = "com.political.app"
SCOPE = "https://www.googleapis.com/auth/androidpublisher"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True, help="서비스 계정 JSON 키 경로")
    ap.add_argument("--aab", help="서명된 AAB 경로 (신규 업로드 시)")
    ap.add_argument("--version-code", type=int, default=None,
                    help="이미 업로드된 versionCode를 프로덕션에 출시만 (업로드 생략)")
    ap.add_argument("--track", default="production",
                    help="production | internal | alpha | beta (기본 production)")
    ap.add_argument("--fraction", type=float, default=None,
                    help="단계적 출시 비율 0~1 (생략 시 100%% 완료)")
    ap.add_argument("--notes", default="Android 16(API 36) 대응 및 안정화",
                    help="ko-KR 출시 노트")
    ap.add_argument("--dry-run", action="store_true",
                    help="업로드까지만 하고 commit 안 함(변경 취소)")
    args = ap.parse_args()

    creds = service_account.Credentials.from_service_account_file(
        args.key, scopes=[SCOPE]
    )
    service = build("androidpublisher", "v3", credentials=creds, cache_discovery=False)
    edits = service.edits()

    try:
        edit_id = edits.insert(packageName=PACKAGE, body={}).execute()["id"]
        print(f"편집 세션 생성: {edit_id}")

        if args.version_code is not None:
            version_code = args.version_code
            print(f"업로드 생략 — 기존 versionCode {version_code} 출시만 진행")
        elif args.aab:
            print(f"AAB 업로드 중... ({args.aab})")
            media = MediaFileUpload(args.aab, mimetype="application/octet-stream",
                                    resumable=True)
            bundle = edits.bundles().upload(
                packageName=PACKAGE, editId=edit_id, media_body=media
            ).execute()
            version_code = bundle["versionCode"]
            print(f"업로드 완료: versionCode {version_code}")
        else:
            print("--aab 또는 --version-code 중 하나는 필요함", file=sys.stderr)
            sys.exit(2)

        release = {
            "versionCodes": [str(version_code)],
            "releaseNotes": [{"language": "ko-KR", "text": args.notes}],
        }
        if args.fraction is not None:
            release["status"] = "inProgress"
            release["userFraction"] = args.fraction
            rollout = f"단계적 {args.fraction*100:.0f}%"
        else:
            release["status"] = "completed"
            rollout = "100% 완료"

        edits.tracks().update(
            packageName=PACKAGE, editId=edit_id, track=args.track,
            body={"releases": [release]},
        ).execute()
        print(f"트랙 '{args.track}' 롤아웃 설정: {rollout}")

        if args.dry_run:
            edits.delete(packageName=PACKAGE, editId=edit_id).execute()
            print("[dry-run] 커밋하지 않고 편집 취소함.")
            return

        edits.commit(packageName=PACKAGE, editId=edit_id).execute()
        print("\n✅ 커밋 완료 — 프로덕션 출시가 시작됐어. 심사 후 반영/경고 해소.")

    except HttpError as e:
        print(f"\n❌ API 오류: {e.status_code} {e.reason}", file=sys.stderr)
        print(e.error_details if hasattr(e, "error_details") else e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
