"""모델 메타데이터/OpenAPI에서 문서를 생성한다.

  python scripts/gen_docs.py   → docs/TABLES.md, docs/ERD.md, docs/API.md, docs/openapi.json
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("ENABLE_BACKGROUND_JOBS", "false")

from sqlalchemy import UniqueConstraint  # noqa: E402
from sqlalchemy.dialects import mysql  # noqa: E402

from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

DOCS = Path(__file__).resolve().parents[1] / "docs"

DOMAINS = {
    "1. Club / Member / Config": ["CLUB", "CLUB_ADMIN", "MEMBER", "SYSTEM_CONFIG", "SYSTEM_CONFIG_HISTORY"],
    "2. Session / Team": ["SESSION", "SESSION_MEMBER", "SESSION_GUEST", "SESSION_TEAM", "SESSION_TEAM_MEMBER",
                          "TEAM_GENERATION", "TEAM_ASSIGNMENT_LOG"],
    "3. Match": ["MATCH_GAME", "MATCH_MEMBER", "MATCH_EVENT"],
    "4. Rating / Stats / Pair / Title": ["PLAYER_RATING", "PLAYER_RATING_HISTORY", "MEMBER_STAT_SUMMARY",
                                         "MEMBER_PAIR_STAT", "TITLE_TYPE", "MEMBER_TITLE"],
    "5. The Wire": ["INSIGHT_TYPE_CONFIG", "INSIGHT_CONFIG_PARAM", "INSIGHT", "INSIGHT_MEMBER", "AI_ARTICLE",
                    "AI_ARTICLE_INSIGHT", "ARTICLE_TAG"],
}
SOURCE = {"CLUB", "MEMBER", "SESSION", "SESSION_MEMBER", "SESSION_GUEST", "SESSION_TEAM", "SESSION_TEAM_MEMBER",
          "MATCH_GAME", "MATCH_MEMBER", "MATCH_EVENT", "MEMBER_TITLE", "TEAM_ASSIGNMENT_LOG"}
DERIVED = {"PLAYER_RATING", "PLAYER_RATING_HISTORY", "MEMBER_STAT_SUMMARY", "MEMBER_PAIR_STAT", "INSIGHT",
           "INSIGHT_MEMBER", "AI_ARTICLE", "AI_ARTICLE_INSIGHT", "ARTICLE_TAG"}


def col_type(c) -> str:
    return str(c.type.compile(dialect=mysql.dialect())).replace("TINYINT(1)", "BOOLEAN")


def kind(t: str) -> str:
    if t in SOURCE:
        return "Source(원본)"
    if t in DERIVED:
        return "Derived(재계산 가능)" if t not in ("PLAYER_RATING_HISTORY", "AI_ARTICLE") else "Derived(이력 보존)"
    return "Config/Reference"


def tables_md() -> str:
    md = ["# Clubwire 테이블 정의서", "",
          "> 자동 생성: `python scripts/gen_docs.py` (원본: app/models, 설명: app/models/comments.py)  ",
          "> MySQL 8.0 / utf8mb4 / InnoDB · 대문자 SNAKE_CASE · BOOLEAN=TINYINT(1) · DATETIME(3)=UTC", ""]
    for dom, names in DOMAINS.items():
        md += [f"## {dom}", ""]
        for name in names:
            t = Base.metadata.tables[name]
            md += [f"### {name}", "", f"{t.comment}  ", f"구분: **{kind(name)}**", "",
                   "| No | 컬럼 | 타입 | NULL | 키 | 설명 |", "|---:|---|---|:---:|---|---|"]
            for i, c in enumerate(t.columns, 1):
                keys = []
                if c.primary_key:
                    keys.append("PK")
                for fk in c.foreign_keys:
                    keys.append(f"FK→{fk.column.table.name}")
                md.append(f"| {i} | `{c.name}` | {col_type(c)} | {'Y' if c.nullable else 'N'} | {' '.join(keys)} | {c.comment or ''} |")
            extra = []
            for cons in t.constraints:
                if isinstance(cons, UniqueConstraint):
                    extra.append(f"- UNIQUE `{cons.name}` ({', '.join(c.name for c in cons.columns)})")
            for c in t.columns:
                if c.unique:
                    extra.append(f"- UNIQUE ({c.name})")
            for ix in sorted(t.indexes, key=lambda x: x.name or ""):
                extra.append(f"- INDEX `{ix.name}` ({', '.join(c.name for c in ix.columns)})")
            if extra:
                md += ["", "제약/인덱스", ""] + extra
            md.append("")
    return "\n".join(md)


def erd_md() -> str:
    md = ["# Clubwire ERD", "", "> 자동 생성: `python scripts/gen_docs.py`. 영역별로 나눠 그렸고, 다른 영역 테이블은 키만 표시.", ""]
    all_tables = Base.metadata.tables
    for dom, names in DOMAINS.items():
        show = set(names)
        rels = []
        for name in names:
            for fk in all_tables[name].foreign_keys:
                parent = fk.column.table.name
                if parent in ("CLUB_ADMIN",) and name not in DOMAINS["1. Club / Member / Config"]:
                    continue  # 감사용 ADMIN_ID 참조는 생략
                if parent == "CLUB" and name not in DOMAINS["1. Club / Member / Config"]:
                    continue  # CLUB_ID 귀속은 전 테이블 공통이라 생략
                show.add(parent)
                one_to_one = fk.parent.primary_key and len(all_tables[name].primary_key.columns) == 1
                card = "||--||" if one_to_one else ("|o--o{" if fk.parent.nullable else "||--o{")
                rels.append(f'    {parent} {card} {name} : "{fk.parent.name}"')
        md += [f"## {dom}", "", "```mermaid", "erDiagram"]
        for name in sorted(show):
            t = all_tables[name]
            md.append(f"    {name} {{")
            for c in t.columns:
                if name not in names and not c.primary_key:
                    continue
                if name in names or c.primary_key:
                    tag = " PK" if c.primary_key else (" FK" if c.foreign_keys else "")
                    typ = col_type(c).split("(")[0].replace(" ", "_")
                    md.append(f"        {typ} {c.name}{tag}")
            md.append("    }")
        md += sorted(set(rels)) + ["```", ""]
    return "\n".join(md)


def _admin_routes() -> set[tuple[str, str]]:
    """admin_dep에 의존하는 (path, METHOD) 집합."""
    from fastapi.routing import APIRoute

    from app.api.deps import admin_dep

    def uses(dep) -> bool:
        return any(d.call is admin_dep or uses(d) for d in dep.dependencies)

    from app.main import CLUB_PREFIX

    out = set()
    stack = [(r, "") for r in app.routes]
    while stack:
        r, prefix = stack.pop()
        inner = getattr(r, "original_router", None)
        if inner is not None:  # FastAPI include_router 래퍼
            stack += [(x, CLUB_PREFIX) for x in inner.routes]
        elif isinstance(r, APIRoute) and uses(r.dependant):
            for m in r.methods:
                out.add((prefix + r.path, m))
    return out


def api_md(spec: dict) -> str:
    md = ["# Clubwire API 목록", "",
          "> 자동 생성(OpenAPI). 상세 스키마는 서버 실행 후 `/docs` 또는 `docs/openapi.json`.  ",
          "> 공통 접두사 `/api/clubs/{club_slug}` · 인증: 🔓 공개 / 🔑 관리자(Bearer 토큰, `POST /admin/auth`로 PIN 입력)", "",
          "| 인증 | Method | Path | 설명 |", "|:---:|---|---|---|"]
    admin_routes = _admin_routes()
    rows = []
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            admin = (path, method.upper()) in admin_routes
            short = path.replace("/api/clubs/{club_slug}", "") or "/"
            rows.append((op.get("tags", ["-"])[0], short, method.upper(), "🔑" if admin else "🔓", op.get("summary", "")))
    order = ["clubs", "members", "sessions", "matches", "stats", "titles", "wire", "system"]
    rows.sort(key=lambda r: (order.index(r[0]) if r[0] in order else 99, r[1], r[2]))
    for tag, path, method, auth, summary in rows:
        md.append(f"| {auth} | {method} | `{path}` | {summary} |")
    md += ["", "WebSocket: `GET /ws/clubs/{club_slug}` (누구나 구독, 메시지 종류는 app/api/ws.py 참고)", ""]
    return "\n".join(md)


def schema_sql() -> str:
    """최종 스키마 DDL(MySQL). 운영 반영은 alembic upgrade head를 사용."""
    from sqlalchemy.schema import CreateIndex, CreateTable

    d = mysql.dialect()
    out = ["-- Clubwire schema (MySQL 8.0, utf8mb4) — 자동 생성: python scripts/gen_docs.py",
           "-- 운영 DB 반영은 'alembic upgrade head' 를 사용하세요. 이 파일은 참고/초기 생성용.", ""]
    for t in Base.metadata.sorted_tables:
        out.append(str(CreateTable(t).compile(dialect=d)).strip() + " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;")
        for ix in sorted(t.indexes, key=lambda x: x.name or ""):
            out.append(str(CreateIndex(ix).compile(dialect=d)).strip() + ";")
        out.append("")
    return "\n".join(out)


def main() -> None:
    DOCS.mkdir(exist_ok=True)
    (DOCS / "schema.sql").write_text(schema_sql(), encoding="utf-8")
    (DOCS / "TABLES.md").write_text(tables_md(), encoding="utf-8")
    (DOCS / "ERD.md").write_text(erd_md(), encoding="utf-8")
    spec = app.openapi()
    (DOCS / "openapi.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    (DOCS / "API.md").write_text(api_md(spec), encoding="utf-8")
    print("docs generated")


if __name__ == "__main__":
    main()
