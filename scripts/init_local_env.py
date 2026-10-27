"""로컬 .env 준비: 다른 설정을 보존하고 비어 있는 서명 키만 생성한다."""
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile


_SECRET_LINE = re.compile(
    r"^(?P<prefix>\ufeff?[ \t]*(?:export[ \t]+)?SECRET_KEY[ \t]*=[ \t]*)(?P<value>[^\r\n]*)",
    flags=re.MULTILINE,
)


def _is_blank(value: str) -> bool:
    return value.strip() in ("", '""', "''")


def _with_secret(contents: str, *, replace_example: bool = False) -> str:
    matches = list(_SECRET_LINE.finditer(contents))
    if not replace_example and any(not _is_blank(m["value"]) for m in matches):
        return contents
    key = secrets.token_hex(32)
    if matches:
        return _SECRET_LINE.sub(lambda m: m["prefix"] + key, contents)
    newline = "\r\n" if "\r\n" in contents else "\n"
    separator = "" if not contents or contents.endswith(("\n", "\r")) else newline
    return contents + separator + "SECRET_KEY=" + key + newline


def env_contents(example: str) -> str:
    return _with_secret(example, replace_example=True)


def _fill_existing(target: Path) -> bool:
    if target.is_symlink():
        raise ValueError("기존 .env가 심볼릭 링크이므로 자동 변경하지 않았습니다.")
    with target.open("rb") as f:
        snapshot = os.fstat(f.fileno())
        original = f.read()
    if not stat.S_ISREG(snapshot.st_mode):
        raise ValueError("기존 .env가 일반 파일이 아니므로 자동 변경하지 않았습니다.")
    contents = original.decode("utf-8")
    prepared = _with_secret(contents)
    if prepared == contents:
        return False

    def unchanged() -> bool:
        current = target.lstat()
        return (stat.S_ISREG(current.st_mode)
                and (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns)
                == (snapshot.st_dev, snapshot.st_ino, snapshot.st_size, snapshot.st_mtime_ns)
                and target.read_bytes() == original)

    temporary: str | None = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=".env.", suffix=".tmp", dir=target.parent)
        with os.fdopen(fd, "wb") as f:
            f.write(prepared.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temporary, 0o600)
        # Replace only the version that was read. A later edit must be retried from its new contents.
        if not unchanged():
            raise RuntimeError(".env가 동시에 변경되어 덮어쓰지 않았습니다. 다시 실행하세요.")
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
    return True


def create_env(project_root: Path) -> bool:
    target = project_root / ".env"
    if target.exists():
        return _fill_existing(target)
    contents = env_contents((project_root / ".env.example").read_bytes().decode("utf-8"))
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return _fill_existing(target)
    with os.fdopen(fd, "wb") as f:
        f.write(contents.encode("utf-8"))
    return True


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    if create_env(root):
        print(".env를 준비하고 새 서명 키를 생성했습니다. OPENAI_API_KEY와 DATABASE_URL을 로컬에서 확인한 뒤 백엔드를 다시 시작하세요.")
    else:
        print("기존 .env의 서명 키와 다른 설정을 그대로 유지했습니다.")


if __name__ == "__main__":
    main()
