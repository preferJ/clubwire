"""Windows MySQL 덤프의 앱 테이블 이름을 Linux 대문자 스키마에 맞춘다.

사용법: python3 scripts/normalize_mysql_dump.py INPUT.sql OUTPUT.sql
원본·기존 출력 파일은 덮어쓰지 않는다. 문자열 데이터와 일반 주석은 바꾸지 않는다.
SQL을 실행하거나 DB에 접속하지 않는 표준 라이브러리 전용 도구다.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path


# app.models.Base.metadata의 테이블명. 런타임에는 SQLAlchemy 설치가 필요 없다.
CANONICAL_TABLE_NAMES = (
    "CLUB", "CLUB_ADMIN", "MEMBER", "SYSTEM_CONFIG", "SYSTEM_CONFIG_HISTORY",
    "MATCH_GAME", "MATCH_MEMBER", "MATCH_EVENT", "PLAYER_RATING", "PLAYER_RATING_HISTORY",
    "SESSION", "SESSION_MEMBER", "SESSION_TEAM", "SESSION_GUEST", "SESSION_TEAM_MEMBER",
    "TEAM_GENERATION", "TEAM_ASSIGNMENT_LOG", "MEMBER_STAT_SUMMARY", "MEMBER_PAIR_STAT",
    "TITLE_TYPE", "MEMBER_TITLE", "INSIGHT_TYPE_CONFIG", "INSIGHT_CONFIG_PARAM",
    "INSIGHT", "INSIGHT_MEMBER", "AI_ARTICLE", "AI_ARTICLE_INSIGHT", "ARTICLE_TAG",
    "alembic_version",
)
_TABLES = {name.lower().encode("ascii"): name.encode("ascii") for name in CANONICAL_TABLE_NAMES}


class DumpSyntaxError(ValueError):
    """완결되지 않은 토큰이 있으면 출력 파일을 만들지 않는다."""


def _quoted_end(data: bytes, start: int, quote: int, offset: int) -> int:
    i = start + 1
    while i < len(data):
        if data[i] == 92:  # MySQL dump 문자열의 backslash escape
            i += 2
        elif data[i] == quote:
            if i + 1 < len(data) and data[i + 1] == quote:
                i += 2
            else:
                return i + 1
        else:
            i += 1
    raise DumpSyntaxError(f"완결되지 않은 SQL 문자열입니다(바이트 {offset + start}).")


def _region(data: bytes, offset: int = 0) -> tuple[bytes, int]:
    pieces: list[bytes] = []
    changes = 0
    i = 0
    while i < len(data):
        char = data[i]
        if char in (39, 34):  # single/double quoted SQL strings
            end = _quoted_end(data, i, char, offset)
            pieces.append(data[i:end])
            i = end
        elif char == 96:  # quoted identifier; doubled backticks escape a literal backtick
            end = i + 1
            token = bytearray()
            while end < len(data):
                if data[end] == 96:
                    if end + 1 < len(data) and data[end + 1] == 96:
                        token.append(96)
                        end += 2
                    else:
                        break
                else:
                    token.append(data[end])
                    end += 1
            if end == len(data):
                raise DumpSyntaxError(f"완결되지 않은 SQL 식별자입니다(바이트 {offset + i}).")
            original = data[i:end + 1]
            canonical = _TABLES.get(bytes(token).lower())
            replacement = b"`" + canonical + b"`" if canonical is not None else original
            changes += replacement != original
            pieces.append(replacement)
            i = end + 1
        elif char == 35 or (data.startswith(b"--", i) and (i + 2 == len(data) or data[i + 2] <= 32)):
            end = data.find(b"\n", i)
            end = len(data) if end == -1 else end + 1
            pieces.append(data[i:end])
            i = end
        elif data.startswith(b"/*", i):
            end = data.find(b"*/", i + 2)
            if end == -1:
                raise DumpSyntaxError(f"완결되지 않은 SQL 주석입니다(바이트 {offset + i}).")
            if data.startswith(b"/*!", i):
                body, count = _region(data[i + 3:end], offset + i + 3)
                pieces.extend((b"/*!", body, b"*/"))
                changes += count
            else:
                pieces.append(data[i:end + 2])
            i = end + 2
        else:
            # Keep arbitrary bytes and original newlines; no text encoding round-trip.
            start = i
            i += 1
            while i < len(data) and data[i] not in (39, 34, 96, 35, 45, 47):
                i += 1
            pieces.append(data[start:i])
    return b"".join(pieces), changes


def normalize_sql(data: bytes) -> bytes:
    """식별자 전체가 알려진 테이블명과 일치할 때만 정규화한다."""
    return _region(data)[0]


def normalize_file(source: Path, destination: Path) -> int:
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError("입력과 출력은 다른 파일이어야 합니다. 원본은 덮어쓰지 않습니다.")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"출력 파일이 이미 있습니다: {destination}")
    prepared, changes = _region(source.read_bytes())
    # Parse the complete dump before creating output, then reserve its name exclusively.
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(prepared)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return changes


def main() -> None:
    parser = argparse.ArgumentParser(description="Windows MySQL 덤프 테이블명을 Clubwire Linux 스키마에 맞게 정규화")
    parser.add_argument("source", type=Path, help="원본 MySQL 덤프(.sql)")
    parser.add_argument("destination", type=Path, help="새 출력 파일(.sql), 기존 파일은 덮어쓰지 않음")
    args = parser.parse_args()
    try:
        changes = normalize_file(args.source, args.destination)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"변환하지 못했습니다: {exc}\n")
    print(f"테이블 식별자 {changes}곳을 정규화했습니다. 원본 파일은 유지했습니다.")
    print(f"출력: {args.destination}")


if __name__ == "__main__":
    main()
