"""운영 CLI.

  python -m app.cli create-club --pin 7777
  python -m app.cli rename-club --from-slug sanha --to-slug ypr --name YPR
  python -m app.cli set-pin --pin 1234
  python -m app.cli seed
"""
import argparse

from app.core.database import SessionLocal
from app.services import club_service
from app.services.common import get_club_by_slug
from app.wire.insight_types import ensure_insight_types


def main() -> None:
    p = argparse.ArgumentParser(prog="clubwire")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-club")
    c.add_argument("--slug", default="ypr")
    c.add_argument("--name", default="YPR")
    c.add_argument("--pin", required=True)
    r = sub.add_parser("rename-club", help="기존 클럽의 기록을 유지하고 주소와 표시 이름 변경")
    r.add_argument("--from-slug", default="sanha")
    r.add_argument("--to-slug", default="ypr")
    r.add_argument("--name", default="YPR")
    s = sub.add_parser("set-pin")
    s.add_argument("--slug", default="ypr")
    s.add_argument("--pin", required=True)
    sub.add_parser("seed")
    args = p.parse_args()

    with SessionLocal() as db:
        if args.cmd == "create-club":
            club = club_service.create_club(db, args.slug, args.name, args.pin)
            print(f"created club #{club.club_id} slug={club.club_slug}")
        elif args.cmd == "rename-club":
            club = club_service.rename_club(db, args.from_slug, args.to_slug, args.name)
            print(f"renamed club #{club.club_id} slug={club.club_slug} name={club.club_name}")
        elif args.cmd == "set-pin":
            club = get_club_by_slug(db, args.slug)
            club_service.set_admin_pin(db, club.club_id, args.pin)
            print("pin updated")
        elif args.cmd == "seed":
            ensure_insight_types(db)
            db.commit()
            print("reference data ok")


if __name__ == "__main__":
    main()
