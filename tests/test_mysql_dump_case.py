"""DB 연결 없이 Windows 덤프의 데이터·주석·인코딩 보존을 검증한다."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.normalize_mysql_dump import CANONICAL_TABLE_NAMES, DumpSyntaxError, normalize_file, normalize_sql


class MysqlDumpCaseTests(unittest.TestCase):
    def test_table_references_and_executable_comments(self):
        source = (b"CREATE TABLE `member` (`MEMBER_ID` bigint, KEY `member_idx` (`MEMBER_ID`));\r\n"
                  b"ALTER TABLE `clubwire`.`session_member` ADD FOREIGN KEY (`MEMBER_ID`) REFERENCES `member` (`MEMBER_ID`);\r\n"
                  b"LOCK TABLES `member` WRITE;\n/*!40000 ALTER TABLE `member` DISABLE KEYS */;\n"
                  b"/*!40000 ALTER TABLE `member` ENABLE KEYS */;\nUNLOCK TABLES;\n"
                  b"INSERT INTO `alembic_version` VALUES ('0009');")
        expected = source.replace(b"`member`", b"`MEMBER`").replace(b"`session_member`", b"`SESSION_MEMBER`")
        self.assertEqual(normalize_sql(source), expected)

    def test_literal_data_comments_and_unknown_identifiers_are_byte_exact(self):
        source = (b"-- `member` is documented here\r\n# `session`\n/* ordinary `club` */\n"
                  b"INSERT INTO `member` VALUES ('literal `member`', 'it\\'s `session`', 'a''`club`', "
                  b"\"double \\\" `member`\", \"doubled \"\" `club`\", 'C:\\\\test', '\xff\xfe');\n"
                  b"CREATE TABLE `unknown` (`member_id` bigint, KEY `member_index` (`member_id`));\n"
                  b"SELECT `we``ird`, `MEMBER`;\n")
        self.assertEqual(normalize_sql(source), source.replace(b"INSERT INTO `member`", b"INSERT INTO `MEMBER`"))

    def test_json_and_unicode_strings_are_preserved(self):
        source = "INSERT INTO `ai_article` VALUES ('{\"text\":\"선수 `member`와 `session`\"}', '기사');\n".encode()
        self.assertEqual(normalize_sql(source), source.replace(b"`ai_article`", b"`AI_ARTICLE`"))

    def test_mysql_double_dash_comment_requires_whitespace(self):
        self.assertEqual(normalize_sql(b"SELECT 1--2, `member`; -- `member`"),
                         b"SELECT 1--2, `MEMBER`; -- `member`")

    def test_malformed_input_is_rejected(self):
        for value in (b"SELECT 'unfinished", b'SELECT "unfinished', b"SELECT `member", b"/* unfinished",
                      b"/*!40000 ALTER TABLE `member`", b"INSERT INTO `member` VALUES ('ends\\"):
            with self.subTest(value=value), self.assertRaises(DumpSyntaxError):
                normalize_sql(value)

    def test_file_creation_keeps_source_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output = root / "original.sql", root / "linux.sql"
            original = b"INSERT INTO `member` VALUES ('kept `member`');\r\n"
            source.write_bytes(original)
            self.assertEqual(normalize_file(source, output), 1)
            self.assertEqual(source.read_bytes(), original)
            expected = output.read_bytes()
            with self.assertRaises(FileExistsError):
                normalize_file(source, output)
            self.assertEqual(output.read_bytes(), expected)
            with self.assertRaises(ValueError):
                normalize_file(source, source)
            self.assertEqual(source.read_bytes(), original)

    def test_parse_failure_creates_no_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output = root / "broken.sql", root / "linux.sql"
            source.write_bytes(b"SELECT 'unterminated")
            with self.assertRaises(DumpSyntaxError):
                normalize_file(source, output)
            self.assertFalse(output.exists())

    def test_cli_has_no_app_dependency(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "normalize_mysql_dump.py"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output = root / "in.sql", root / "out.sql"
            source.write_bytes(b"CREATE TABLE `club` (`CLUB_ID` bigint);")
            run = subprocess.run([sys.executable, "-S", str(script), str(source), str(output)], capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr.decode())
            self.assertEqual(output.read_bytes(), b"CREATE TABLE `CLUB` (`CLUB_ID` bigint);")

    def test_mapping_covers_current_model_tables(self):
        from app.models import Base
        self.assertEqual(set(CANONICAL_TABLE_NAMES), set(Base.metadata.tables) | {"alembic_version"})


if __name__ == "__main__":
    unittest.main()
