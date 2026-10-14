"""ORM 공통 정의.

명명 규칙: 테이블/컬럼은 대문자 SNAKE_CASE(MEMBER_ID). 파이썬 속성은 소문자.
- BOOLEAN 컬럼은 문서 명명(…_YN)을 유지하되 타입은 BOOLEAN(TINYINT(1)).
- 상태값은 VARCHAR + app/models/enums.py.
- DATETIME은 UTC, 밀리초 정밀도.
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, MetaData
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.timeutil import utcnow

NAMING_CONVENTION = {
    "ix": "IX_%(table_name)s_%(column_0_N_name)s",
    "uq": "UQ_%(table_name)s_%(column_0_N_name)s",
    "ck": "CK_%(table_name)s_%(constraint_name)s",
    "fk": "FK_%(table_name)s_%(column_0_name)s",
    "pk": "PK_%(table_name)s",
}

UtcDateTime = DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql")
Id = BigInteger


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column("CREATED_AT", UtcDateTime, nullable=False, default=utcnow)


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        "UPDATED_AT", UtcDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
