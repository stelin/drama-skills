import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SUITE = Path(__file__).resolve().parents[1]
SCRIPT = SUITE / "skills/short-drama-novel-analyze/scripts/novel_index.py"
SPEC = importlib.util.spec_from_file_location("short_drama_novel_index", SCRIPT)
assert SPEC and SPEC.loader
novel_index = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(novel_index)


def prose(lines: int = 30) -> str:
    return "\n".join("正文内容这一行大约二十来个字符。" for _ in range(lines))


def chapters(numbers: list[str], title: str = "标题") -> str:
    return "\n\n".join(f"第{number}章 {title}\n{prose()}" for number in numbers)


class ChineseNumeralTests(unittest.TestCase):
    def test_reads_the_forms_serialized_fiction_actually_uses(self) -> None:
        cases = {
            "一": 1,
            "十": 10,
            "十五": 15,
            "二十三": 23,
            "一百零三": 103,
            "两百": 200,
            "两百零三": 203,
            "一千零一": 1001,
            "一千二百三十四": 1234,
            "123": 123,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(novel_index.chinese_to_int(text), expected)

    def test_unreadable_numeral_is_reported_not_raised(self) -> None:
        # A crash here would leave the creator with no boundary table at all,
        # rather than a table with one flagged row.
        self.assertIsNone(novel_index.chinese_to_int("甲"))
        self.assertIsNone(novel_index.chinese_to_int(""))


class ChapterIndexTests(unittest.TestCase):
    def build(self, text: str) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "book.txt"
            source.write_text(text, encoding="utf-8")
            return novel_index.build_index(source)

    def test_plain_source_indexes_every_chapter(self) -> None:
        index = self.build(chapters(["一", "二", "三", "四", "五", "六"]) + "\n")
        self.assertEqual(index["chapter_count"], 6)
        self.assertEqual(index["contents_entries_dropped"], 0)
        self.assertEqual(index["problems"], [])
        self.assertEqual(
            [chapter["source_number"] for chapter in index["chapters"]],
            [1, 2, 3, 4, 5, 6],
        )

    def test_leading_contents_block_is_dropped(self) -> None:
        numbers = ["一", "二", "三", "四", "五", "六"]
        contents = "\n".join(f"第{number}章 目录条目" for number in numbers)
        index = self.build(contents + "\n\n" + chapters(numbers) + "\n")
        self.assertEqual(index["contents_entries_dropped"], 6)
        self.assertEqual(index["chapter_count"], 6)
        # Every surviving chapter must carry real prose; a contents entry would
        # slice to a body of almost nothing and be reported as a problem.
        self.assertEqual(index["problems"], [])
        for chapter in index["chapters"]:
            self.assertGreater(chapter["char_count"], 100)

    def test_multi_volume_restart_is_flagged_not_dropped(self) -> None:
        # Each volume restarting at 第一章 is a legal structure. Treating the
        # first volume as a contents block would delete a sixth of the book.
        text = chapters(["一", "二", "三"]) + "\n\n" + chapters(["一", "二", "三"])
        index = self.build(text + "\n")
        self.assertEqual(index["chapter_count"], 6)
        self.assertEqual(index["contents_entries_dropped"], 0)
        self.assertTrue(index["volume_numbering_restarts"])
        self.assertEqual(index["problems"], [])

    def test_dense_opening_that_is_not_a_contents_block_survives(self) -> None:
        # Short opening chapters whose numbers never reappear are story, not an
        # index, so density alone must not delete them.
        dense = "\n".join(f"第{number}章 短章" for number in ["一", "二", "三"])
        text = dense + "\n\n" + chapters(["四", "五", "六"]) + "\n"
        index = self.build(text)
        self.assertEqual(index["contents_entries_dropped"], 0)
        self.assertEqual(index["chapter_count"], 6)

    def test_numbering_jump_is_reported(self) -> None:
        index = self.build(chapters(["一", "二", "五"]) + "\n")
        self.assertTrue(
            any("jumps" in problem for problem in index["problems"]),
            index["problems"],
        )

    def test_source_with_no_heading_reports_rather_than_inventing_spans(self) -> None:
        index = self.build(prose() + "\n")
        self.assertEqual(index["chapter_count"], 0)
        self.assertTrue(index["problems"])

    def test_spans_reconstruct_the_source_exactly(self) -> None:
        numbers = ["一", "二", "三"]
        text = chapters(numbers) + "\n"
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "book.txt"
            source.write_text(text, encoding="utf-8")
            index = novel_index.build_index(source)
            index_path = Path(directory) / "index.json"
            index_path.write_text(
                json.dumps(index, ensure_ascii=False), encoding="utf-8"
            )
            self.assertTrue(novel_index.verify_index(index_path, source)["verified"])

            # A source edited after indexing must invalidate the index, because
            # every span and every citation built on it now points elsewhere.
            source.write_text("插入一行\n" + text, encoding="utf-8")
            result = novel_index.verify_index(index_path, source)
            self.assertFalse(result["verified"])
            self.assertTrue(result["problems"])


class CoverageTests(unittest.TestCase):
    def test_missing_chapter_blocks_completion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.txt"
            source.write_text(chapters(["一", "二", "三", "四"]) + "\n", encoding="utf-8")
            index_path = root / "index.json"
            index_path.write_text(
                json.dumps(novel_index.build_index(source), ensure_ascii=False),
                encoding="utf-8",
            )
            analysis = root / "章节"
            analysis.mkdir()
            for sequence in (1, 2, 4):
                (analysis / f"第{sequence}章-提取.md").write_text("x", encoding="utf-8")

            result = novel_index.coverage(index_path, analysis)
            self.assertEqual(result["missing"], [3])
            self.assertFalse(result["complete"])
            self.assertEqual(result["present"], 3)

    def test_complete_coverage_reports_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.txt"
            source.write_text(chapters(["一", "二"]) + "\n", encoding="utf-8")
            index_path = root / "index.json"
            index_path.write_text(
                json.dumps(novel_index.build_index(source), ensure_ascii=False),
                encoding="utf-8",
            )
            analysis = root / "章节"
            analysis.mkdir()
            for sequence in (1, 2):
                (analysis / f"第{sequence}章-提取.md").write_text("x", encoding="utf-8")

            result = novel_index.coverage(index_path, analysis)
            self.assertTrue(result["complete"])
            self.assertEqual(result["missing"], [])


if __name__ == "__main__":
    unittest.main()
