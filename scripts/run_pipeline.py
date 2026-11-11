"""수집 파이프라인 단일 진입점. GitHub Actions와 /api/sources/ingest가 같은 함수를 쓴다.

가벼운 단계(뉴스 RSS 수집)는 매 실행, 무거운 단계는 마지막 실행 후 3시간 이상 지났을 때, 의원 보강은 KST 하루 1회. 모든 단계가 PipelineContext를
공유해 기사·이슈·소스를 실행당 한 번만 읽고, 끝에 `[meter] reads=N writes=N gemini=N`을 남긴다.

실행: python scripts/run_pipeline.py [--heavy] [--steps a,b,c]
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.pipeline_steps import select_steps  # noqa: E402
from utils.ai_budget import KST  # noqa: E402


async def run_pipeline(steps=None, heavy=None, daily=None) -> dict:
    from firebase.firebase_config import db
    from utils.read_meter import ReadMeter
    from utils.ai_budget import budget
    from services.pipeline_context import firestore_context

    meter = ReadMeter()
    meter.install()
    ctx = firestore_context(db)
    results = {}
    # 무거운/일간 단계는 시계 시각이 아니라 _meta/pipeline_state의 마지막 실행 기록으로 판정(크론 누락 대비)
    from datetime import timezone as _utc_tz
    from utils.pipeline_steps import heavy_due, daily_due
    now_utc = datetime.now(_utc_tz.utc)
    state_ref = db.collection("_meta").document("pipeline_state")
    state = {}
    if steps is None and (heavy is None or daily is None):
        try:
            snap = state_ref.get()
            state = (snap.to_dict() or {}) if snap.exists else {}
        except Exception:  # noqa: BLE001 — 상태 조회 실패면 가벼운 단계만
            state = {"_unreadable": True}
    if heavy is None and steps is None:
        heavy = False if state.get("_unreadable") else heavy_due(state.get("last_heavy_at"), now_utc)
    if daily is None and steps is None:
        daily = False if state.get("_unreadable") else daily_due(state.get("last_daily_date"), now_utc)
    plan = select_steps(datetime.now(KST).hour, heavy=heavy, only=steps, daily=daily)
    try:
        for step in plan:
            before = meter.snapshot()
            try:
                results[step] = await _run_step(step, ctx)
            except Exception as e:  # noqa: BLE001 — 한 단계 실패가 다음 단계를 막지 않는다
                results[step] = {"success": False, "message": repr(e)}
            after = meter.snapshot()
            print(f"[{step}] reads+={after['reads'] - before['reads']} writes+={after['writes'] - before['writes']} "
                  f"{str(results[step])[:300]}")
        if steps is None:
            patch = {}
            if heavy:
                patch["last_heavy_at"] = now_utc.isoformat()
            if daily:
                patch["last_daily_date"] = now_utc.astimezone(KST).strftime("%Y-%m-%d")
            if patch:
                try:
                    state_ref.set(patch, merge=True)
                except Exception as e:  # noqa: BLE001
                    print(f"[pipeline_state] {e!r}")
    finally:
        snap = meter.snapshot()
        meter.uninstall()
        used = budget().used()
        print(f"[meter] reads={snap['reads']} writes={snap['writes']} gemini={used}")
        if snap["reads"] > 2000:
            print(f"[meter] WARNING reads {snap['reads']} > 2000 (읽기 예산 초과)")
    return {"steps": plan, "results": results, "meter": snap}


async def _run_step(step: str, ctx):
    if step == "collect_news":
        from services.news_service import news_service
        return await news_service.collect_news_from_rss()
    from services.source_ingest_service import source_ingest_service as ing
    if step == "ingest_gov":
        return await ing.ingest_gov_policy()
    if step == "ingest_bills":
        return await ing.ingest_assembly_bills()
    if step == "ingest_votes":
        return await ing.ingest_assembly_votes()
    if step == "enrich_pending":
        return await ing.enrich_pending(ctx=ctx)
    from services.issue_cluster_service import issue_cluster_service
    if step == "generate_bill_issues":
        return await issue_cluster_service.generate_bill_issues(ctx=ctx)
    from services.source_link_service import source_link_service as link
    if step == "link_unlinked":
        return await link.link_unlinked(ctx=ctx)
    if step == "crosslink":
        return await link.crosslink(ctx=ctx)
    from services.news_issue_service import news_issue_service as nis
    if step == "generate_news_issues":
        return await nis.generate_news_issues(ctx=ctx)
    if step == "link_news_issues":
        if os.getenv("LINK_NEWS_ISSUES", "0").strip() not in ("1", "true", "yes", "on"):
            return {"success": True, "message": "비활성(LINK_NEWS_ISSUES=0)", "data": {}}
        return await link.link_news_issues(ctx=ctx)
    if step == "summarize_pending_issues":
        return await nis.summarize_pending_issues(ctx=ctx)
    from services.issue_digest_service import issue_digest_service
    if step == "refresh_digest":
        return issue_digest_service.refresh(ctx=ctx)
    from services.edition_service import edition_service
    if step == "build_edition":
        return edition_service.build(ctx=ctx)
    from services.member_service import member_service as ms
    if step == "enrich_member_bills":
        return await ms.enrich_member_bills()
    if step == "enrich_member_votes":
        return await ms.enrich_member_votes()
    raise ValueError(f"unknown step {step}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--heavy", action="store_true", help="무거운 단계를 마지막 실행 기록과 무관하게 실행")
    ap.add_argument("--daily", action="store_true", help="의원 보강(일 1회 단계)을 시각과 무관하게 실행")
    ap.add_argument("--steps", default=None, help="쉼표 구분 단계 목록만 실행")
    args = ap.parse_args(argv)
    steps = [s.strip() for s in args.steps.split(",")] if args.steps else None
    out = asyncio.run(run_pipeline(steps=steps, heavy=True if args.heavy else None,
                                   daily=True if args.daily else None))
    failed = [k for k, v in out["results"].items() if not (v or {}).get("success", True)]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
