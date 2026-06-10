"""의원 샘플 데이터를 Firestore에 적재한다(가공 예시).
사용: FIREBASE_* env 설정 후 python scripts/seed_members.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.model import MemberCreate
from services.member_service import member_service


async def main() -> None:
    path = Path(__file__).resolve().parent.parent / "data" / "sample_members.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    count = 0
    for item in raw:
        result = await member_service.upsert_member(MemberCreate(**item))
        if result.get("success"):
            count += 1
        else:
            print("skip:", result.get("message"))
    print(f"seeded {count} members")


if __name__ == "__main__":
    asyncio.run(main())
