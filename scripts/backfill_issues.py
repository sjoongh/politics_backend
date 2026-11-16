"""이슈 문서 일회성 backfill. 기본 dry-run, --apply 시 변경 전 대상 문서를 backups/에 JSONL 덤프.

서브커맨드:
  article-meta   article_ids → article_meta 채우고 article_ids를 날짜 역순으로 정렬
  digest         모든 활성 이슈의 digest 재계산(press 제외), active 없는 문서에 active=True
  summary-flags  템플릿 요약("여러 매체가 보도한 현안입니다"/"…1차 소스를 묶은 이슈입니다")을 규칙 기반 대체 요약으로 교체, ai_summarized=False
  links          source_items의 issue_id/link_status → links[]·issue_ids 변환(변경 문서만)
  prune-crosslink 뉴스 이슈에서 인용구 규칙에 안 맞는 기사 연결 제거(인명 단독 오염 정정)
  retire         지정한 이슈를 비활성(active=False)으로(--ids a,b). 문서는 지우지 않는다(공유 링크 유지)
  procedural     표결·법안 소스의 procedural 플래그를 현재 규칙으로 재계산
  retitle        뉴스 이슈: 인물(빈도 기준)·인용구 중심 제목·요약(인용구 담은 기사 우선, 영어 AI 요약 교체)·소강 상태
                 법안 이슈: 요약을 표결 결과·표결일로, 보도 없는 절차안 이슈 비활성

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


def cmd_links(apply: bool) -> int:
    from firebase.firebase_config import db
    from utils.source_links import add_link
    docs = [{**d.to_dict(), "id": d.id} for d in db.collection("source_items").stream()]
    patches = []
    for s_ in docs:
        if s_.get("links") or not s_.get("issue_id") or s_.get("link_status") not in ("auto", "confirmed", "pending", "rejected"):
            continue
        ln = add_link(s_, s_["issue_id"], s_["link_status"], 0.0, "legacy", s_.get("updated_at") or "")
        patches.append((s_["id"], {k: ln[k] for k in ("links", "issue_ids", "issue_id", "link_status")}))
    print(f"sources={len(docs)} to_update={len(patches)} reads={len(docs)}")
    if not apply:
        print("dry-run (no writes). --apply to write.")
        return 0
    ids = {p_[0] for p_ in patches}
    path = dump_backup("links", [d for d in docs if d["id"] in ids])
    for sid, p_ in patches:
        db.collection("source_items").document(sid).update(p_)
    print(f"applied={len(patches)} backup={path}")
    return 0


def cmd_prune_crosslink(apply: bool) -> int:
    from firebase.firebase_config import db
    from utils.crosslink_match import article_matches_issue
    from utils.article_meta import sorted_article_ids
    issues = [{**d.to_dict(), "id": d.id} for d in db.collection("issues").stream()
              if str(d.to_dict().get("auto_key") or "").startswith("news:") and d.to_dict().get("active") is not False]
    need = sorted({a for i in issues for a in (i.get("article_ids") or [])})
    arts = {}
    for chunk in _chunks(need, 300):
        for snap in db.get_all([db.collection("articles").document(a) for a in chunk]):
            if snap.exists:
                arts[snap.id] = snap.to_dict()
    patches, backups, removed_total = [], [], 0
    for iss in issues:
        keep, drop = [], []
        for aid in (iss.get("article_ids") or []):
            a = arts.get(aid)
            blob = ((a or {}).get("title") or "") + " " + ((a or {}).get("ai_summary") or "")
            (keep if a is None or article_matches_issue(blob, iss, min_tokens=1) else drop).append(aid)
        if drop:
            keep_set = set(keep)
            meta = {k: v for k, v in (iss.get("article_meta") or {}).items() if k in keep_set}
            ordered = sorted_article_ids(meta) + [k for k in keep if k not in meta]
            patches.append((iss["id"], {"article_ids": ordered, "article_meta": meta}))
            backups.append({"id": iss["id"], "article_ids": iss.get("article_ids"), "article_meta": iss.get("article_meta"),
                            "digest": iss.get("digest")})
            removed_total += len(drop)
            print(f"  {iss.get('title')}: {len(iss.get('article_ids') or [])} → {len(keep)} (-{len(drop)})")
    print(f"news_issues={len(issues)} to_update={len(patches)} removed_links={removed_total} reads={len(issues) + len(need)}")
    if not apply:
        print("dry-run (no writes). --apply to write.")
        return 0
    path = dump_backup("prune-crosslink", backups)
    for iid, p_ in patches:
        db.collection("issues").document(iid).update(p_)
    from services.issue_digest_service import issue_digest_service
    # 이번에 바꾼 이슈 + 이전 실행이 중단돼 digest가 기사 수와 어긋난 이슈까지 재계산(재실행 복구)
    stale = [i["id"] for i in issues if ((i.get("digest") or {}).get("counts") or {}).get("media") not in (None, len(i.get("article_meta") or {}))]
    targets = sorted({iid for iid, _ in patches} | set(stale))
    issue_digest_service.refresh(issue_ids=targets, press=False)
    print(f"applied={len(patches)} digest_refreshed={len(targets)} backup={path}")
    return 0


READ_GUARD = 15000   # backfill 한 번이 하루 무료 읽기(5만)의 30%를 넘지 않게


def cmd_retire(apply: bool, ids: list, reason: str) -> int:
    from firebase.firebase_config import db
    snaps = [db.collection("issues").document(i).get() for i in ids]
    docs = [{**s_.to_dict(), "id": s_.id} for s_ in snaps if s_.exists]
    for d in docs:
        print(f"  {d['id']}: {d.get('title')} active={d.get('active')} rank={(d.get('digest') or {}).get('rank')}")
    missing = sorted(set(ids) - {d["id"] for d in docs})
    print(f"targets={len(docs)} missing={missing}")
    if not apply:
        print("dry-run (no writes). --apply to write.")
        return 0
    path = dump_backup("retire", [{"id": d["id"], "active": d.get("active"), "retired_reason": d.get("retired_reason")} for d in docs])
    now = datetime.now(timezone.utc).isoformat()
    for d in docs:
        db.collection("issues").document(d["id"]).update({"active": False, "retired_reason": reason, "updated_at": now})
    print(f"applied={len(docs)} backup={path}")
    return 0


def cmd_procedural(apply: bool) -> int:
    from firebase.firebase_config import db
    from utils.law_name import is_procedural
    # 표결·법안 전수(일부만 고치면 생성 단계의 any(procedural)가 옛 판정을 계속 본다). 개수 집계 1회로 예산 확인.
    n_est = 0
    for t in ("assembly_vote", "assembly_bill"):
        n_est += db.collection("source_items").where("type", "==", t).count().get()[0][0].value
    if n_est > READ_GUARD:
        print(f"대상 {n_est}건 > 읽기 가드 {READ_GUARD} — 중단(하루 무료 읽기 5만 보호)")
        return 1
    docs = []
    for t in ("assembly_vote", "assembly_bill"):
        docs += [{**d.to_dict(), "id": d.id} for d in db.collection("source_items").where("type", "==", t).stream()]
    patches = []
    for d in docs:
        name = (d.get("title") or "").replace("표결: ", "", 1)
        new = is_procedural(name)
        if bool(d.get("procedural")) != new:
            patches.append((d["id"], new, name))
    flips = sum(1 for _, n, _ in patches if n)
    print(f"sources={len(docs)} to_update={len(patches)} (→절차안 {flips}, →실질 {len(patches) - flips}) reads={len(docs)}")
    for sid, n, name in patches[:12]:
        print(f"  {'절차' if n else '실질'} | {name[:70]}")
    if not apply:
        print("dry-run (no writes). --apply to write.")
        return 0
    ids = {p_[0] for p_ in patches}
    path = dump_backup("procedural", [{"id": d["id"], "procedural": d.get("procedural")} for d in docs if d["id"] in ids])
    for sid, n, _ in patches:
        db.collection("source_items").document(sid).update({"procedural": n})
    print(f"applied={len(patches)} backup={path}")
    return 0


def _retitle_news(iss: dict, arts: list, known: set, now) -> dict:
    """뉴스 이슈 1건의 새 필드(바뀌는 것만). arts: 이슈의 최근 기사(최대 20)."""
    from collections import Counter
    from utils.news_entities import extract_entities
    from utils.issue_merge import clean_title
    from utils.fallback_summary import fallback_summary
    from utils.gemini_rest import is_korean
    from utils.issue_digest import news_status
    cur_people = (iss.get("entities") or {}).get("people") or []
    kws = iss.get("keywords") or []
    phrase = kws[0] if kws and kws[0] not in cur_people else ""
    cnt = Counter()
    for a in arts:
        for n in extract_entities(a.get("title"), a.get("ai_summary"), known).get("names") or []:
            cnt[n] += 1
    people = [n for n, _ in sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))] or list(cur_people)
    person = people[0] if people else None
    new = {"title": clean_title(person, phrase),
           "keywords": [k for k in ([phrase] + people) if k][:6],
           "entities": {**(iss.get("entities") or {}), "people": people}}
    probe = {**iss, **new}
    if not iss.get("ai_summarized") or not is_korean(iss.get("summary") or ""):
        new["summary"] = fallback_summary(probe, {a["id"]: a for a in arts})
        new["ai_summarized"] = False
    st = news_status(iss, (iss.get("digest") or {}).get("last_activity_at"), now)
    if st:
        new["status"] = st
    return {k: v for k, v in new.items() if iss.get(k) != v}


def _retitle_bill(iss: dict) -> dict:
    from utils.fallback_summary import fallback_summary
    from utils.law_name import is_procedural
    dg = iss.get("digest") or {}
    new = {}
    rec = (dg.get("vote") or {}).get("date") or dg.get("last_official_at")
    if rec and not iss.get("record_date"):
        new["record_date"] = str(rec)[:10]
    if not iss.get("ai_summarized"):
        new["summary"] = fallback_summary({**iss, **new}, {})
    media = len(iss.get("article_meta") or {}) or len(iss.get("article_ids") or [])
    if is_procedural(iss.get("title") or "") and media == 0:
        new["active"] = False
        new["inactive_reason"] = "gate"   # 규칙 기반 비활성: 보도가 생기면 파이프라인이 복귀시킨다
    return {k: v for k, v in new.items() if iss.get(k) != v}


def cmd_retitle(apply: bool) -> int:
    from firebase.firebase_config import db
    from services.pipeline_context import firestore_context
    issues = [{**d.to_dict(), "id": d.id} for d in db.collection("issues").stream()
              if d.to_dict().get("active") is not False]
    news = [i for i in issues if str(i.get("auto_key") or "").startswith("news:")]
    bills = [i for i in issues if str(i.get("auto_key") or "").startswith("bill:")]
    known = firestore_context(db).member_names()
    def recent_ids(i):
        meta = i.get("article_meta") or {}
        ids = sorted(meta, key=lambda k: (meta[k] or {}).get("at") or "", reverse=True)
        ids = ids or list(i.get("article_ids") or [])
        return list(dict.fromkeys(ids[:25] + ids[-5:]))   # 최근 25 + 처음 묶인 5(인용구 원문이 있는 기사)
    need = sorted({a for i in news for a in recent_ids(i)})
    if len(issues) + len(need) > READ_GUARD:
        print(f"예상 읽기 {len(issues) + len(need)} > 읽기 가드 {READ_GUARD} — 중단")
        return 1
    arts = {}
    for chunk in _chunks(need, 300):
        for snap in db.get_all([db.collection("articles").document(a) for a in chunk]):
            if snap.exists:
                arts[snap.id] = {**snap.to_dict(), "id": snap.id}
    now = datetime.now(timezone.utc)
    patches = []
    for i in news:
        p_ = _retitle_news(i, [arts[a] for a in recent_ids(i) if a in arts], known, now)
        if p_:
            patches.append((i, p_))
    for i in bills:
        p_ = _retitle_bill(i)
        if p_:
            patches.append((i, p_))
    print(f"issues={len(issues)} news={len(news)} bills={len(bills)} to_update={len(patches)} reads≈{len(issues) + len(need) + 1}")
    for i, p_ in patches:
        line = f"  [{i['id'][:22]}] {i.get('title')!s:.34}"
        if "title" in p_:
            line += f" → {p_['title']}"
        if "status" in p_:
            line += f" | 상태 {i.get('status')}→{p_['status']}"
        if p_.get("active") is False:
            line += " | 비활성"
        print(line)
        if "summary" in p_:
            print(f"      요약: {str(i.get('summary'))[:40]!r} → {p_['summary'][:50]!r}")
    if not apply:
        print("dry-run (no writes). --apply to write.")
        return 0
    keys = sorted({k for _, p_ in patches for k in p_})
    path = dump_backup("retitle", [{"id": i["id"], **{k: i.get(k) for k in keys}} for i, _ in patches])
    for i, p_ in patches:
        db.collection("issues").document(i["id"]).update(p_)
    print(f"applied={len(patches)} backup={path}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("article-meta", "digest", "summary-flags", "links", "prune-crosslink", "retire", "procedural", "retitle"):
        p = sub.add_parser(name)
        p.add_argument("--apply", action="store_true")
        if name == "retire":
            p.add_argument("--ids", required=True)
            p.add_argument("--reason", default="샘플 데이터 정리")
    args = ap.parse_args(argv)
    if args.cmd == "retire":
        return cmd_retire(args.apply, [x.strip() for x in args.ids.split(",") if x.strip()], args.reason)
    if args.cmd == "procedural":
        return cmd_procedural(args.apply)
    if args.cmd == "retitle":
        return cmd_retitle(args.apply)
    if args.cmd == "article-meta":
        return cmd_article_meta(args.apply)
    if args.cmd == "digest":
        return cmd_digest(args.apply)
    if args.cmd == "summary-flags":
        return cmd_summary_flags(args.apply)
    if args.cmd == "links":
        return cmd_links(args.apply)
    if args.cmd == "prune-crosslink":
        return cmd_prune_crosslink(args.apply)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
