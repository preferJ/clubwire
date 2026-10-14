"""SYSTEM_CONFIG 조회/변경(+이력, 버전)."""
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.club_config import CONFIG_DEF_MAP, CONFIG_DEFS, ClubConfig, parse_value, serialize_value
from app.core.errors import BadRequest
from app.models import Club, SystemConfig, SystemConfigHistory


def seed_club_config(db: Session, club_id: int) -> None:
    existing = set(db.scalars(select(SystemConfig.config_key).where(SystemConfig.club_id == club_id)))
    for d in CONFIG_DEFS:
        if d.key not in existing:
            db.add(
                SystemConfig(
                    club_id=club_id,
                    config_key=d.key,
                    config_value=serialize_value(d, d.default),
                    value_type=d.value_type,
                    description=d.description,
                )
            )


def load_config(db: Session, club_id: int) -> ClubConfig:
    club = db.get(Club, club_id)
    values: dict[str, Any] = {d.key: d.default for d in CONFIG_DEFS}
    for row in db.scalars(select(SystemConfig).where(SystemConfig.club_id == club_id)):
        d = CONFIG_DEF_MAP.get(row.config_key)
        if d:
            values[d.key] = parse_value(d, row.config_value)
    return ClubConfig(values, version=club.config_version if club else 0)


def list_config(db: Session, club_id: int) -> list[dict[str, Any]]:
    cfg = load_config(db, club_id)
    return [
        {
            "key": d.key,
            "value": cfg[d.key],
            "valueType": d.value_type,
            "defaultValue": d.default,
            "description": d.description,
            "choices": list(d.choices) or None,
        }
        for d in CONFIG_DEFS
    ]


def update_config(db: Session, club_id: int, changes: dict[str, Any], admin_id: int | None) -> ClubConfig:
    """설정 변경 + 이력 + 버전 증가를 한 트랜잭션으로."""
    if not changes:
        raise BadRequest("변경할 값이 없습니다.")
    club = db.execute(select(Club).where(Club.club_id == club_id).with_for_update()).scalar_one()
    rows = {r.config_key: r for r in db.scalars(select(SystemConfig).where(SystemConfig.club_id == club_id))}
    parsed: dict[str, tuple[Any, str]] = {}
    for key, raw in changes.items():
        d = CONFIG_DEF_MAP.get(key)
        if not d:
            raise BadRequest(f"알 수 없는 설정 키: {key}", "UNKNOWN_CONFIG")
        v = parse_value(d, raw)
        parsed[key] = (v, serialize_value(d, v))

    changed = [(k, sv) for k, (_, sv) in parsed.items() if not rows.get(k) or rows[k].config_value != sv]
    if not changed:
        db.rollback()
        return load_config(db, club_id)

    club.config_version += 1
    for key, sv in changed:
        d = CONFIG_DEF_MAP[key]
        row = rows.get(key)
        before = row.config_value if row else None
        if row:
            row.config_value = sv
        else:
            db.add(SystemConfig(club_id=club_id, config_key=key, config_value=sv, value_type=d.value_type,
                                description=d.description))
        db.add(
            SystemConfigHistory(
                club_id=club_id, config_key=key, before_value=before, after_value=sv,
                config_version=club.config_version, changed_by_admin_id=admin_id,
            )
        )
    db.commit()
    return load_config(db, club_id)


def config_history(db: Session, club_id: int, limit: int = 100) -> list[SystemConfigHistory]:
    return list(
        db.scalars(
            select(SystemConfigHistory)
            .where(SystemConfigHistory.club_id == club_id)
            .order_by(SystemConfigHistory.history_id.desc())
            .limit(limit)
        )
    )
