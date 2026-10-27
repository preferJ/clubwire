"""YPR 테스트 시작용 로컬 DB 초기화.

미리보기(변경 없음): python -m scripts.reset_ypr_test
백업 후 적용:        python -m scripts.reset_ypr_test --apply

먼저 백엔드를 종료하세요. .env의 DATABASE_URL에서 지정한 DB 중 --club의
기록만 초기화합니다. 클럽·관리자 PIN·설정·타이틀 정의는 보존합니다.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
from decimal import Decimal
import json
import math
import os
from pathlib import Path
import secrets
from typing import Any

from sqlalchemy import JSON, delete, func, select, update
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.timeutil import utcnow
from app.models import AiArticle, ArticleTag, Base, Club, Member, MemberStatSummary
from app.models.enums import ArticleStatus, ArticleType
from app.services.config_service import load_config
from app.services.rating_service import ensure_player_rating


# scripts/gen_sample_data.py ROSTER 및 ypr_sample_data.sql의 전달받은 초기 표와 동일.
# 샘플 생성기는 import 시 환경변수를 바꾸므로 여기서는 원본 값을 독립적으로 보관한다.
ROSTER = (
    ("손원일", 1081), ("김응철", 1078), ("안휘진", 1078), ("유창우", 1075), ("전원재", 1060), ("김현섭", 1054),
    ("윤기창", 1054), ("이종훈", 1048), ("김상균", 1024), ("박영현", 1015), ("이용준", 1006), ("변현우", 997),
    ("김재홍", 991), ("김동근", 979), ("이민선", 973), ("권태홍", 970), ("진선호", 967), ("임우철", 952),
    ("이채현", 928), ("김승준", 922), ("윤영문", 922), ("구대현", 916), ("김병채", 910),
)

NOTICE_TITLE = "YPR clubWire 테스트 기간 돌입"
NOTICE_SUMMARY = "참석부터 팀 편성, 경기 기록과 기사까지 한곳에서. YPR의 새로운 경기 운영 도구 clubWire를 함께 써보세요."
NOTICE_BODY = """YPR이 clubWire 테스트 기간에 들어갑니다. 참석 명단을 정리하고, 팀을 나누고, 경기 기록을 확인하던 일을 이제 한곳에서 이어갑니다. 복잡한 설명부터 읽기보다는 선수단에서 내 이름을 찾고 와이어 소식을 둘러보는 것부터 시작해 보세요.

선수단에서는 선수별 경기 기록을 볼 수 있고, 화면 맨 위의 운영 수칙도 바로 열어볼 수 있습니다. 기록실에서는 골·도움·승률과 수상 내역을 확인할 수 있습니다. 아직 경기를 뛰기 전이라면 기록이 비어 있는 것이 정상입니다. 이제부터 한 경기씩 채워 가면 됩니다.

운영진은 자물쇠 버튼으로 관리자 모드에 들어간 뒤 일정을 만들고 참석자와 게스트를 등록합니다. 팀 편성을 확인하고 [일정확정]을 누르면 프리뷰 기사 검토 화면으로 이동합니다. 기사는 내용을 고치거나 다시 쓰고, 반려하거나 게시할 수 있습니다. 확정만 했다고 프리뷰가 바로 공개되지는 않습니다.

경기를 진행할 때는 [다음 경기 만들기]에서 대진을 고르고 시작합니다. 골과 도움을 입력하고, 잘못 입력한 골은 취소할 수 있습니다. 타이머로 경기 흐름을 확인한 뒤 [기록 확정]으로 마무리하고, 모든 경기가 끝나면 [일정마감]을 진행하면 됩니다. 경기 화면은 실시간으로 갱신되고, 확정한 기록은 통계와 수상 내역에 이어집니다.

와이어에서는 일정의 관전 포인트와 마감 기사를 읽을 수 있습니다. 기사에 담지 않은 기록 도전은 하단 이정표 표에서 챙겨 보고, 이달의 MVP 후보도 확인해 보세요. 테스트 중 헷갈리는 버튼이나 실제 경기 흐름과 맞지 않는 부분이 보이면 운영진에게 알려 주세요. 함께 써보면서 YPR에 맞는 사용법을 찾아가겠습니다."""

# 정의/접속 정보를 보존하고, 해당 클럽의 경기·선수·파생 데이터만 지운다.
PRESERVED_TABLES = {
    "CLUB", "CLUB_ADMIN", "SYSTEM_CONFIG", "SYSTEM_CONFIG_HISTORY", "TITLE_TYPE",
    "INSIGHT_TYPE_CONFIG", "INSIGHT_CONFIG_PARAM",
}
SCOPE_COLUMNS = {
    "INSIGHT_MEMBER": "INSIGHT_ID", "ARTICLE_TAG": "ARTICLE_ID", "AI_ARTICLE_INSIGHT": "ARTICLE_ID",
    "TEAM_ASSIGNMENT_LOG": "SESSION_ID", "MATCH_MEMBER": "MATCH_ID", "MATCH_EVENT": "MATCH_ID",
    "INSIGHT": "CLUB_ID", "AI_ARTICLE": "CLUB_ID", "SESSION_TEAM_MEMBER": "SESSION_ID",
    "SESSION_GUEST": "SESSION_ID", "MATCH_GAME": "SESSION_ID", "SESSION_TEAM": "SESSION_ID",
    "TEAM_GENERATION": "SESSION_ID", "SESSION_MEMBER": "SESSION_ID", "PLAYER_RATING_HISTORY": "CLUB_ID",
    "PLAYER_RATING": "CLUB_ID", "MEMBER_TITLE": "CLUB_ID", "MEMBER_STAT_SUMMARY": "CLUB_ID",
    "MEMBER_PAIR_STAT": "CLUB_ID", "SESSION": "CLUB_ID", "MEMBER": "CLUB_ID",
}
SELF_REFS = {"AI_ARTICLE": "PARENT_ARTICLE_ID", "MATCH_EVENT": "REF_EVENT_ID"}
DEFAULT_BACKUP_DIR = Path(__file__).resolve().parents[1] / ".venv" / "clubwire-reset-backups"


def _tables():
    unknown = set(Base.metadata.tables) - PRESERVED_TABLES - set(SCOPE_COLUMNS)
    if unknown:
        raise RuntimeError(f"초기화 범위가 정의되지 않은 테이블이 있습니다: {', '.join(sorted(unknown))}")
    return [t for t in Base.metadata.sorted_tables if t.name in SCOPE_COLUMNS]


def _ids(db: Session, club_id: int) -> dict[str, list[int]]:
    t = Base.metadata.tables
    sessions = select(t["SESSION"].c.SESSION_ID).where(t["SESSION"].c.CLUB_ID == club_id)
    return {
        "SESSION_ID": list(db.scalars(sessions)),
        "MEMBER_ID": list(db.scalars(select(t["MEMBER"].c.MEMBER_ID).where(t["MEMBER"].c.CLUB_ID == club_id))),
        "MATCH_ID": list(db.scalars(select(t["MATCH_GAME"].c.MATCH_ID).where(t["MATCH_GAME"].c.SESSION_ID.in_(sessions)))),
        "ARTICLE_ID": list(db.scalars(select(t["AI_ARTICLE"].c.ARTICLE_ID).where(t["AI_ARTICLE"].c.CLUB_ID == club_id))),
        "INSIGHT_ID": list(db.scalars(select(t["INSIGHT"].c.INSIGHT_ID).where(t["INSIGHT"].c.CLUB_ID == club_id))),
    }


def _scope(table, club_id: int, ids: dict[str, list[int]]):
    key = SCOPE_COLUMNS[table.name]
    return table.c[key] == club_id if key == "CLUB_ID" else table.c[key].in_(ids[key])


def preview_reset(db: Session, club: Club) -> dict[str, int]:
    """부작용 없는 클럽별 초기화 대상 행 수."""
    ids = _ids(db, club.club_id)
    return {t.name: int(db.scalar(select(func.count()).select_from(t).where(_scope(t, club.club_id, ids))) or 0)
            for t in _tables()}


def _quote(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def _sql_value(value: Any, column=None) -> str:
    """SQL 모드/문자열 escape 방식에 의존하지 않는 MySQL 리터럴."""
    if value is None:
        return "NULL"
    if column is not None and isinstance(column.type, JSON):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, Decimal)):
        if isinstance(value, Decimal) and not value.is_finite():
            raise ValueError("백업할 수 없는 숫자입니다.")
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("백업할 수 없는 숫자입니다.")
        return repr(value)
    if isinstance(value, (date, datetime)):
        return "'" + value.isoformat(sep=" ") + "'" if isinstance(value, datetime) else "'" + value.isoformat() + "'"
    if isinstance(value, str):
        return "CONVERT(X'" + value.encode("utf-8").hex() + "' USING utf8mb4)"
    if isinstance(value, bytes):
        return "X'" + value.hex() + "'"
    raise TypeError(f"백업할 수 없는 데이터 형식: {type(value).__name__}")


def _restore_scope(table, club_id: int) -> str:
    key = SCOPE_COLUMNS[table.name]
    if key == "CLUB_ID":
        return f"`CLUB_ID` = {club_id}"
    lookup = {
        "SESSION_ID": f"SELECT `SESSION_ID` FROM `SESSION` WHERE `CLUB_ID` = {club_id}",
        "MATCH_ID": ("SELECT `MATCH_ID` FROM `MATCH_GAME` WHERE `SESSION_ID` IN "
                     f"(SELECT `SESSION_ID` FROM `SESSION` WHERE `CLUB_ID` = {club_id})"),
        "ARTICLE_ID": f"SELECT `ARTICLE_ID` FROM `AI_ARTICLE` WHERE `CLUB_ID` = {club_id}",
        "INSIGHT_ID": f"SELECT `INSIGHT_ID` FROM `INSIGHT` WHERE `CLUB_ID` = {club_id}",
    }
    return f"{_quote(key)} IN ({lookup[key]})"


def _backup_sql(db: Session, club: Club, rows: dict[str, list[dict]], path: Path) -> None:
    """보존된 클럽·설정 위에 초기화 전 데이터를 복구하는 SQL을 작성한다."""
    database = db.get_bind().url.database
    if not database:
        raise RuntimeError("복구 SQL을 만들려면 DATABASE_URL에 DB 이름이 필요합니다.")
    club_id = club.club_id
    tables = _tables()
    lines = [
        "-- Clubwire YPR reset backup. Backend must be stopped before restore.",
        "-- Restore only to the original database and preserved club. No credentials are included.",
        "-- In the MySQL client: USE the original database; SOURCE this file;",
        "START TRANSACTION;",
        "SET @CW_RESTORE_OK = (SELECT COUNT(*) = 1 FROM `CLUB` WHERE "
        f"`CLUB_ID` = {club_id} AND BINARY `CLUB_SLUG` = BINARY {_sql_value(club.club_slug)} "
        f"AND BINARY DATABASE() = BINARY {_sql_value(database)});",
    ]
    for name, col in SELF_REFS.items():
        table = Base.metadata.tables[name]
        lines.append(f"UPDATE {_quote(name)} SET {_quote(col)} = NULL WHERE @CW_RESTORE_OK = 1 AND {_restore_scope(table, club_id)};")
    for table in reversed(tables):
        lines.append(f"DELETE FROM {_quote(table.name)} WHERE @CW_RESTORE_OK = 1 AND {_restore_scope(table, club_id)};")
    deferred = []
    for table in tables:
        columns = list(table.columns)
        names = ", ".join(_quote(c.name) for c in columns)
        self_ref = SELF_REFS.get(table.name)
        for row in rows[table.name]:
            values = ["NULL" if c.name == self_ref else _sql_value(row[c.name], c) for c in columns]
            lines.append(f"INSERT INTO {_quote(table.name)} ({names}) SELECT {', '.join(values)} WHERE @CW_RESTORE_OK = 1;")
            if self_ref and row[self_ref] is not None:
                primary = " AND ".join(f"{_quote(c.name)} = {_sql_value(row[c.name], c)}" for c in table.primary_key.columns)
                deferred.append(f"UPDATE {_quote(table.name)} SET {_quote(self_ref)} = {_sql_value(row[self_ref])} "
                                f"WHERE @CW_RESTORE_OK = 1 AND {primary};")
    lines.extend(deferred)
    lines.extend(["COMMIT;", "SELECT IF(@CW_RESTORE_OK = 1, 'RESTORED', 'SKIPPED: database/club identity mismatch') AS CLUBWIRE_RESTORE;"])
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
        f.flush()
        os.fsync(f.fileno())


def reset_club(db: Session, club: Club, backup_dir: Path = DEFAULT_BACKUP_DIR) -> dict:
    """해당 클럽만 백업·초기화하고 선수단과 안내 기사 생성까지 한 번에 커밋한다."""
    if db.get_bind().dialect.name != "mysql":
        raise RuntimeError("이 초기화/SQL 백업은 MySQL용입니다.")
    try:
        club = db.scalar(select(Club).where(Club.club_id == club.club_id).with_for_update())
        if club is None or not club.active_yn:
            raise RuntimeError("초기화할 활성 클럽이 없습니다.")
        tables = _tables()
        ids = _ids(db, club.club_id)
        rows = {t.name: [dict(r) for r in db.execute(select(t).where(_scope(t, club.club_id, ids))
                                                   .order_by(*t.primary_key.columns).with_for_update()).mappings()]
                for t in tables}
        backup = Path(backup_dir).resolve() / f"clubwire-{club.club_id}-{utcnow():%Y%m%dT%H%M%S%fZ}-{secrets.token_hex(4)}.sql"
        _backup_sql(db, club, rows, backup)
        for name, col in SELF_REFS.items():
            table = Base.metadata.tables[name]
            db.execute(update(table).where(_scope(table, club.club_id, ids)).values({col: None}))
        for table in reversed(tables):
            db.execute(delete(table).where(_scope(table, club.club_id, ids)))
        cfg = load_config(db, club.club_id)
        for position, (name, rating) in enumerate(ROSTER):
            member = Member(club_id=club.club_id, name=name, display_order=position,
                            active_yn=True, initial_rating=float(rating))
            db.add(member)
            db.flush()
            ensure_player_rating(db, member, cfg)
            db.add(MemberStatSummary(member_id=member.member_id, club_id=club.club_id))
        article = AiArticle(club_id=club.club_id, article_type=ArticleType.NOTICE,
                            title=NOTICE_TITLE, summary=NOTICE_SUMMARY, content=NOTICE_BODY,
                            model_name="manual", prompt_version="manual_notice_v1", status=ArticleStatus.PUBLISHED,
                            published_yn=True, published_at=utcnow(), generation_no=1,
                            request_json={"kind": "ypr_test_launch"})
        db.add(article)
        db.flush()
        db.add_all([ArticleTag(article_id=article.article_id, tag_name=tag) for tag in ("공지", "테스트 안내")])
        result = {"backup_path": backup, "club_id": club.club_id, "member_count": len(ROSTER), "article_id": article.article_id}
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="YPR 선수단 원본·테스트 안내 기사로 클럽 기록 초기화(기본: 미리보기)")
    parser.add_argument("--club", default="sanha", help="초기화할 클럽 slug (기본: sanha)")
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR, help="초기화 전 복구 SQL 저장 폴더")
    parser.add_argument("--apply", action="store_true", help="백업 후 실제 초기화. 먼저 백엔드를 종료하세요.")
    args = parser.parse_args()
    with SessionLocal() as db:
        url = db.get_bind().url
        print(f"대상 DB: host={url.host or 'localhost'}, port={url.port or 3306}, database={url.database}")
        club = db.scalar(select(Club).where(Club.club_slug == args.club))
        if club is None:
            raise SystemExit("클럽을 찾지 못했습니다. DATABASE_URL과 --club을 확인하세요.")
        print(f"대상 클럽: {club.club_slug} (ID {club.club_id}, {club.club_name})")
        counts = preview_reset(db, club)
        for name, count in counts.items():
            if count:
                print(f"  {name}: {count}행")
        print(f"등록 예정: 원본 선수 {len(ROSTER)}명, 경기·통계 0부터 시작")
        print(f"게시 예정: {NOTICE_TITLE}")
        print("보존: 다른 클럽, 관리자 PIN, 클럽 설정, 타이틀 정의")
        if not args.apply:
            print("미리보기만 수행했습니다. 백엔드 종료 후 같은 명령에 --apply를 붙이면 초기화합니다.")
            return
        result = reset_club(db, club, args.backup_dir)
        print(f"초기화 완료: 선수 {result['member_count']}명, 게시 기사 1건")
        print(f"복구 SQL: {result['backup_path']}")


if __name__ == "__main__":
    main()
