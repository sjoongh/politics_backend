import pytest
from pydantic import ValidationError
from models.model import CriminalRecord, MemberCreate


def test_criminal_record_requires_source_url():
    rec = CriminalRecord(offense="공직선거법위반", disposition="벌금 100만원", year="2021", source_url="http://nec/1")
    assert rec.is_final is True
    assert rec.source_url == "http://nec/1"
    with pytest.raises(ValidationError):
        CriminalRecord(offense="x", disposition="y")  # source_url 누락


def test_member_create_defaults():
    m = MemberCreate(name="홍길동")
    assert m.party is None
    assert m.criminal_records == []


def test_member_create_with_records():
    m = MemberCreate(
        name="홍길동", party="무소속", district="서울 중구",
        criminal_records=[{"offense": "도로교통법위반", "disposition": "벌금 50만원", "year": "2019", "source_url": "http://nec/2"}],
    )
    assert isinstance(m.criminal_records[0], CriminalRecord)
    assert m.criminal_records[0].is_final is True
