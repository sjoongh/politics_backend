"""중복 뉴스 이슈 병합(일회성). 기본 dry-run: 병합 쌍 표를 출력·저장한다.
--apply: 백업 덤프 → 남는 문서에 기사·메타·이벤트·키워드 합치기 → 흡수 문서 merged_into/active=False
        → 흡수 문서를 가리키던 source_items의 issue_id/issue_ids/links를 남는 id로 치환.

실행: .venv/bin/python scripts/merge_duplicate_issues.py [--report /tmp/merge-report.md] [--apply]
"""
import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.backfill_issues import dump_backup  # noqa: E402


def _merged_doc(keep: dict, gone: dict) -> dict:
    from utils.article_meta import sorted_article_ids
    meta = {**(gone.get("article_meta") or {}), **(keep.get("article_meta") or {})}
    ordered = sorted_article_ids(meta)
    known = set(ordered)
    tail = [i for i in (keep.get("article_ids") or []) + (gone.get("article_ids") or []) if i not in known]
    tail = list(dict.fromkeys(tail))
    events, seen = [], set()
    for ev in (keep.get("events") or []) + (gone.get("events") or []):
        k = ev.get("id") or (ev.get("date"), ev.get("headline"))
        if k in seen:
            continue
        seen.add(k)
        events.append(ev)
    kws = list(dict.fromkeys((keep.get("keywords") or []) + (gone.get("keywords") or [])))[:8]
    people = list(dict.fromkeys(((keep.get("entities") or {}).get("people") or [])
                                + ((gone.get("entities") or {}).get("people") or [])))
    ent = {**(keep.get("entities") or {}), "people": people}
    return {"article_meta": meta, "article_ids": ordered + tail, "events": events, "keywords": kws,
            "entities": ent, "updated_at": datetime.now(timezone.utc).isoformat()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--report", default=None)
    args = ap.parse_args(argv)

    from firebase.firebase_config import db
    from utils.issue_merge import merge_plan
    now = datetime.now(timezone.utc)
    issues = [{**d.to_dict(), "id": d.id} for d in db.collection("issues").stream()]
    by_id = {i["id"]: i for i in issues}
    pairs = merge_plan(issues, now)

    lines = [f"# 병합 dry-run {now.isoformat()}", "", f"이슈 {len(issues)}개 중 병합 쌍 {len(pairs)}개", "",
             "| 흡수될 이슈 | → 남는 이슈 | 기사 | 겹침 |", "|---|---|---|---|"]
    for gone_id, keep_id in pairs:
        g, k = by_id[gone_id], by_id[keep_id]
        ga, ka = set(g.get("article_ids") or []), set(k.get("article_ids") or [])
        ov = len(ga & ka) / max(1, min(len(ga), len(ka))) if ga and ka else 0
        lines.append(f"| {g.get('title')} (`{gone_id}`) | {k.get('title')} (`{keep_id}`) | {len(ga)}→{len(ka)} | {ov:.2f} |")
    report = "\n".join(lines)
    print(report)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(report + "\n")
    if not args.apply:
        print("\ndry-run (no writes). --apply to merge.")
        return 0

    backup = dump_backup("merge-issues", [by_id[g] for g, _ in pairs] + [by_id[k] for _, k in pairs])
    moved_sources = 0
    for gone_id, keep_id in pairs:
        keep, gone = by_id[keep_id], by_id[gone_id]
        patch = _merged_doc(keep, gone)
        db.collection("issues").document(keep_id).update(patch)
        keep.update(patch)
        db.collection("issues").document(gone_id).update(
            {"merged_into": keep_id, "active": False, "updated_at": patch["updated_at"]})
        seen = set()
        for q in (db.collection("source_items").where("issue_id", "==", gone_id),
                  db.collection("source_items").where("issue_ids", "array_contains", gone_id)):
            for d in q.stream():
                if d.id in seen:
                    continue
                seen.add(d.id)
                s = d.to_dict()
                sp = {}
                if s.get("issue_id") == gone_id:
                    sp["issue_id"] = keep_id
                if gone_id in (s.get("issue_ids") or []):
                    sp["issue_ids"] = list(dict.fromkeys([keep_id if i == gone_id else i for i in s["issue_ids"]]))
                if s.get("links"):
                    sp["links"] = [{**l, "issue_id": keep_id} if l.get("issue_id") == gone_id else l for l in s["links"]]
                if sp:
                    d.reference.update(sp)
                    moved_sources += 1
    print(f"merged={len(pairs)} sources_moved={moved_sources} backup={backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
