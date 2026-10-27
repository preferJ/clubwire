"""Oracle 배포 설정 생성. 실제 값은 출력하지 않고 기존 설정은 보존한다."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import secrets
import tempfile


_GENERATED = ("MYSQL_ROOT_PASSWORD", "MYSQL_PASSWORD", "SECRET_KEY")
_LINE = re.compile(r"^([A-Z_][A-Z0-9_]*)=(.*)$", flags=re.MULTILINE)
_HOST = re.compile(r"(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$")


def _values(contents: str) -> dict[str, str]:
    return {m[1]: m[2].strip() for m in _LINE.finditer(contents)}


def prepare_env(contents: str, domain: str | None = None) -> str:
    """빈 비밀값만 생성하고, 기존 비밀값과 사용자가 입력한 API 키는 변경하지 않는다."""
    existing = _values(contents)
    if domain is not None and not _HOST.fullmatch(domain):
        raise ValueError("도메인은 https:// 또는 경로 없이 입력하세요. 예: myclub.duckdns.org")
    if domain and existing.get("DOMAIN") and domain != existing["DOMAIN"]:
        raise ValueError("기존 DOMAIN을 보존했습니다. 변경하려면 deploy/oracle.env를 직접 수정하세요.")
    updates = {name: secrets.token_hex(32) for name in _GENERATED if not existing.get(name)}
    if domain and not existing.get("DOMAIN"):
        updates["DOMAIN"] = domain
    result = _LINE.sub(lambda m: m[1] + "=" + updates[m[1]] if m[1] in updates else m[0], contents)
    missing = [name for name in updates if name not in existing]
    if missing:
        result = result.rstrip("\r\n") + "\n" + "\n".join(name + "=" + updates[name] for name in missing) + "\n"
    values = _values(result)
    if values.get("DOMAIN") and not _HOST.fullmatch(values["DOMAIN"]):
        raise ValueError("DOMAIN은 실제 호스트 이름이어야 합니다. 예: myclub.duckdns.org")
    if len(values["SECRET_KEY"]) < 32:
        raise ValueError("기존 SECRET_KEY가 너무 짧습니다. 32자 이상의 값을 설정하세요.")
    if not re.fullmatch(r"[A-Za-z0-9_.~-]{32,}", values["MYSQL_PASSWORD"]):
        raise ValueError("MYSQL_PASSWORD는 URL에 안전한 영문·숫자·._~- 32자 이상을 사용하세요.")
    if len(values["MYSQL_ROOT_PASSWORD"]) < 32:
        raise ValueError("기존 MYSQL_ROOT_PASSWORD가 너무 짧습니다. 32자 이상의 값을 설정하세요.")
    return result


def create_deploy_env(project_root: Path, domain: str | None = None) -> bool:
    target = project_root / "deploy" / "oracle.env"
    if target.is_symlink():
        raise ValueError("deploy/oracle.env가 심볼릭 링크이므로 자동 수정하지 않습니다.")
    original = target.read_bytes() if target.exists() else None
    source = original.decode("utf-8") if original is not None else (target.parent / "oracle.env.example").read_text(encoding="utf-8")
    prepared = prepare_env(source, domain).encode("utf-8")
    if prepared == original:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    if original is None:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(prepared)
        return True
    temporary: str | None = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=".oracle.env.", suffix=".tmp", dir=target.parent)
        with os.fdopen(fd, "wb") as f:
            f.write(prepared)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temporary, 0o600)
        if target.is_symlink() or target.read_bytes() != original:
            raise RuntimeError("배포 설정이 동시에 수정되어 덮어쓰지 않았습니다. 다시 실행하세요.")
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Oracle 배포용 비밀값 생성(기존 값 유지)")
    parser.add_argument("--domain", help="예: myclub.duckdns.org (https:// 없이)")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    changed = create_deploy_env(root, args.domain)
    print("deploy/oracle.env를 준비했습니다." if changed else "기존 배포 설정을 그대로 유지했습니다.")
    print("DOMAIN과 선택 사항 OPENAI_API_KEY를 확인하세요. 실제 설정값은 출력하지 않았습니다.")
    print("실행: docker compose --env-file deploy/oracle.env -f compose.production.yml up -d --build")


if __name__ == "__main__":
    main()
