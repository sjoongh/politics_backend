"""이슈 문서 일회성 backfill. 기본 dry-run, --apply 시 변경 전 대상 문서를 backups/에 JSONL 덤프.

서브커맨드:
  article-meta   article_ids → article_meta 채우고 article_ids를 날짜 역순으로 정렬
  digest         모든 활성 이슈의 digest 재계산(press 제외), active 없는 문서에 active=True
  summary-flags  템플릿 요약("여러 매체가 보도한 현안입니다"/"…1차 소스를 묶은 이슈입니다")을 규칙 기반 대체 요약으로 교체, ai_summarized=False
  (links 는 후속 작업에서 추가)

실행: .venv/bin/python scripts/backfill_issues.py article-meta [--apply]
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def dump_backup(name: str, docs: list) -> str:
    os.makedirs("backups", exist_ok=True)
    path = f"backups/{name}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False, default=str) + "\n")
    return path


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def cmd_article_meta(apply: bool) -> int:
    from firebase.firebase_config import db
    from utils.article_meta import attach_articles

    issues = [{**d.to_dict(), "id": d.id} for d in db.collection("issues").stream()]
    reads = len(issues)
    all_ids = sorted({a for i in issues for a in (i.get("article_ids") or [])})
    found = {}
    for chunk in _chunks(all_ids, 300):
        refs = [db.collection("articles").document(a) for a in chunk]
        for snap in db.get_all(refs):
            reads += 1
            if snap.exists:
                found[snap.id] = {**snap.to_dict(), "id": snap.id}
    missing = [a for a in all_ids if a not in found]
    patches, backups = [], []
    for iss in issues:
        arts = [found[a] for a in (iss.get("article_ids") or []) if a in found]
        patch = attach_articles({"article_ids": iss.get("article_ids") or [], "article_meta": {}}, arts)
        if patch["article_meta"] != (iss.get("article_meta") or {}) or patch["article_ids"] != (iss.get("article_ids") or []):
            patches.append((iss["id"], patch))
            backups.append({"id": iss["id"], "article_ids": iss.get("article_ids"), "article_meta": iss.get("article_meta")})
    print(f"issues={len(issues)} articles={len(all_ids)} found={len(found)} missing={len(missing)} "
          f"to_update={len(patches)} reads={reads}")
    if not apply:
        print("dry-run (no writes). --apply to write.")
        return 0
    path = dump_backup("article-meta", backups)
    for issue_id, patch in patches:
        db.collection("issues").document(issue_id).update(patch)
    print(f"applied={len(patches)} backup={path}")
    return 0


def cmd_digest(apply: bool) -> int:
    from firebase.firebase_config import db
    from services.issue_digest_service import issue_digest_service, _same_digest
    from utils.issue_digest import build_digest
    from datetime import datetime as _dt, timezone as _tz
    issues = [{**d.to_dict(), "id": d.id} for d in db.collection("issues").stream()
              if d.to_dict().get("active") is not False]
    now = _dt.now(_tz.utc)
    changed, backups = 0, []
    for iss in issues:
        sources = issue_digest_service._sources_for(iss["id"])
        dg = build_digest(iss, sources, now, press_stance=[])
        if not _same_digest(iss.get("digest"), dg) or iss.get("active") is None:
            changed += 1
            backups.append({"id": iss["id"], "digest": iss.get("digest"), "active": iss.get("active")})
    print(f"issues={len(issues)} to_update={changed} (reads≈{len(issues) * 3})")
    if not apply:
        print("dry-run (no writes). --apply to write.")
        return 0
    path = dump_backup("digest", backups)
    out = issue_digest_service.refresh(issue_ids=None, press=False)
    print(f"applied={out['data']['updated']} backup={path}")
    return 0


TEMPLATE_MARKERS = ("여러 매체가 보도한 현안입니다", "1차 소스를 묶은 이슈입니다")


def cmd_summary_flags(apply: bool) -> int:
    from firebase.firebase_config import db
    from utils.fallback_summary import fallback_summary
    issues = [{**d.to_dict(), "id": d.id} for d in db.collection("issues").stream()]
    targets = [i for i in issues if any(m in (i.get("summary") or "") for m in TEMPLATE_MARKERS)]
    need = sorted({a for i in targets for a in (i.get("article_ids") or [])[:5]})
    arts = {}
    for chunk in _chunks(need, 300):
        for snap in db.get_all([db.collection("articles").document(a) for a in chunk]):
            if snap.exists:
                arts[snap.id] = snap.to_dict()
    patches = [(i["id"], {"summary": fallback_summary(i, arts), "ai_summarized": False}) for i in targets]
    print(f"issues={len(issues)} template_summaries={len(targets)} reads={len(issues) + len(need)}")
    for iid, p in patches[:5]:
        print(f"  {iid}: {p['summary'][:60]}")
    if not apply:
        print("dry-run (no writes). --apply to write.")
        return 0
    path = dump_backup("summary-flags", [{"id": i["id"], "summary": i.get("summary"),
                                          "ai_summarized": i.get("ai_summarized")} for i in targets])
    for iid, p in patches:
        db.collection("issues").document(iid).update(p)
    print(f"applied={len(patches)} backup={path}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("article-meta", "digest", "summary-flags"):
        p = sub.add_parser(name)
        p.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "article-meta":
        return cmd_article_meta(args.apply)
    if args.cmd == "digest":
        return cmd_digest(args.apply)
    if args.cmd == "summary-flags":
        return cmd_summary_flags(args.apply)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
