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
            "entities": ent, "active": True, "updated_at": datetime.now(timezone.utc).isoformat()}


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

    backup_docs = [by_id[g] for g, _ in pairs] + [by_id[k] for _, k in pairs]
    backup_docs += [{"_source_item": True, **s_} for s_ in _sources_pointing(db, [g for g, _ in pairs])]
    backup = dump_backup("merge-issues", backup_docs)
    moved_sources = 0
    for gone_id, keep_id in pairs:
        moved_sources += apply_pair(db, by_id, gone_id, keep_id)
    repaired = repair_orphans(db)
    print(f"merged={len(pairs)} sources_moved={moved_sources} orphans_repaired={repaired} backup={backup}")
    return 0


def _sources_pointing(db, issue_ids):
    seen, out = set(), []
    for iid in issue_ids:
        for q in (db.collection("source_items").where("issue_id", "==", iid),
                  db.collection("source_items").where("issue_ids", "array_contains", iid)):
            for d in q.stream():
                if d.id in seen:
                    continue
                seen.add(d.id)
                out.append({**d.to_dict(), "id": d.id})
    return out


def _move_sources(db, gone_id, keep_id) -> int:
    """gone_id를 가리키는 source_items를 keep_id로 치환(멱등). links는 issue_id 기준 중복 제거."""
    moved = 0
    for s_ in _sources_pointing(db, [gone_id]):
        sp = {}
        if s_.get("issue_id") == gone_id:
            sp["issue_id"] = keep_id
        if gone_id in (s_.get("issue_ids") or []):
            sp["issue_ids"] = list(dict.fromkeys([keep_id if i == gone_id else i for i in s_["issue_ids"]]))
        if s_.get("links"):
            seen_l, links = set(), []
            for l in [{**l, "issue_id": keep_id} if l.get("issue_id") == gone_id else l for l in s_["links"]]:
                if l.get("issue_id") in seen_l:
                    continue
                seen_l.add(l.get("issue_id"))
                links.append(l)
            sp["links"] = links
        if sp:
            db.collection("source_items").document(s_["id"]).update(sp)
            moved += 1
    return moved


def apply_pair(db, by_id, gone_id, keep_id) -> int:
    """순서: 남는 문서 갱신 → 소스 이관 → digest 재계산 → 마지막에 흡수 문서 표시.
    중간에 실패해도 흡수 문서가 아직 active라 재실행의 merge_plan이 다시 잡는다."""
    from services.issue_digest_service import issue_digest_service
    keep, gone = by_id[keep_id], by_id[gone_id]
    patch = _merged_doc(keep, gone)
    db.collection("issues").document(keep_id).update(patch)
    keep.update(patch)
    moved = _move_sources(db, gone_id, keep_id)
    issue_digest_service.refresh(issue_ids=[keep_id], press=False)
    db.collection("issues").document(gone_id).update(
        {"merged_into": keep_id, "active": False, "updated_at": patch["updated_at"]})
    return moved


def repair_orphans(db) -> int:
    """이미 merged_into가 있는데 소스가 아직 옛 id를 가리키면 이관을 마저 한다(중단된 이전 실행 복구)."""
    from utils.issue_merge_rules import follow_merge
    fixed = 0
    merged = [{**d.to_dict(), "id": d.id} for d in db.collection("issues").where("active", "==", False).stream()]
    lookup = {m["id"]: m for m in merged}
    for m in merged:
        if not m.get("merged_into"):
            continue
        target = follow_merge(m["id"], lambda i: lookup.get(i) or (db.collection("issues").document(i).get().to_dict()))
        if target != m["id"]:
            fixed += _move_sources(db, m["id"], target)
    return fixed


if __name__ == "__main__":
    raise SystemExit(main())
