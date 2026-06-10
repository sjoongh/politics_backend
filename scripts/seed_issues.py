"""이슈 샘플 데이터를 Firestore에 적재한다.
사용: FIREBASE_* env(.env) 설정 후 python scripts/seed_issues.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.model import IssueSeed, EventSeed
from services.issue_service import issue_service


async def main() -> None:
    path = Path(__file__).resolve().parent.parent / "data" / "sample_issues.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    count = 0
    for item in raw:
        events = item.pop("events", [])
        result = await issue_service.create(IssueSeed(**item))
        if not result.get("success"):
            print("skip:", result.get("message"))
            continue
        issue_id = result["data"]["id"]
        for ev in events:
            await issue_service.add_event(issue_id, EventSeed(**ev))
        count += 1
    print(f"seeded {count} issues")


if __name__ == "__main__":
    asyncio.run(main())
