#!/usr/bin/env python3
import argparse
import re
import sys
from collections import Counter
from pathlib import Path
import unicodedata

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CLEANED_DIR = BASE_DIR / "cleaned"
KEYWORDS_DIR = BASE_DIR / "keywords"
SUMMARY_PATH = BASE_DIR / "summary.txt"
KEYWORDS_PATH = BASE_DIR / "keywords.txt"


PUNCT_TRANSLATION = str.maketrans(
    {
        "，": ",",
        "。": ".",
        "：": ":",
        "；": ";",
        "？": "?",
        "！": "!",
        "（": "(",
        "）": ")",
        "【": "[",
        "】": "]",
        "《": "<",
        "》": ">",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
    }
)


def read_text(path: Path) -> str:
    encodings = ["utf-8", "utf-8-sig", "gb18030"]
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(PUNCT_TRANSLATION)
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"\s+", " ", line)
        lines.append(line)
    cleaned = "\n".join(lines)
    return cleaned.lower()


def normalize_for_match(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(PUNCT_TRANSLATION)
    text = text.lower()
    text = re.sub(r"[\s\W]+", "", text)
    return text


def load_keywords() -> list[str]:
    if not KEYWORDS_PATH.exists():
        raise FileNotFoundError(f"keywords.txt not found at {KEYWORDS_PATH}")
    keywords = []
    for line in KEYWORDS_PATH.read_text(encoding="utf-8").splitlines():
        keyword = line.strip()
        if keyword:
            keywords.append(keyword)
    return keywords


def ensure_dirs() -> None:
    CLEANED_DIR.mkdir(exist_ok=True)
    KEYWORDS_DIR.mkdir(exist_ok=True)


def clean_all() -> None:
    ensure_dirs()
    for path in sorted(DATA_DIR.glob("*.txt")):
        content = read_text(path)
        cleaned = clean_text(content)
        (CLEANED_DIR / path.name).write_text(cleaned, encoding="utf-8")


def match_keywords() -> dict[str, list[str]]:
    ensure_dirs()
    keywords = load_keywords()
    matches_by_teacher: dict[str, list[str]] = {}
    normalized_keywords = [(kw, normalize_for_match(kw)) for kw in keywords]

    for path in sorted(CLEANED_DIR.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        normalized_text = normalize_for_match(text)
        found = []
        for keyword, normalized_keyword in normalized_keywords:
            if keyword.lower() in text or (
                normalized_keyword and normalized_keyword in normalized_text
            ):
                found.append(keyword)
        matches_by_teacher[path.stem] = found
        (KEYWORDS_DIR / path.name).write_text("\n".join(found), encoding="utf-8")
    return matches_by_teacher


def build_summary(matches_by_teacher: dict[str, list[str]]) -> str:
    keywords = load_keywords()
    keyword_counts = Counter()
    for _, matches in matches_by_teacher.items():
        for keyword in set(matches):
            keyword_counts[keyword] += 1

    lines = ["[关键词命中统计]"]
    for keyword in keywords:
        lines.append(f"{keyword}: {keyword_counts.get(keyword, 0)}")

    lines.append("")
    lines.append("[命中关键词最多的教师 Top3]")
    teacher_counts = {
        teacher: len(set(matches)) for teacher, matches in matches_by_teacher.items()
    }
    top_teachers = sorted(
        teacher_counts.items(), key=lambda item: (-item[1], item[0])
    )[:3]
    if top_teachers:
        for teacher, count in top_teachers:
            lines.append(f"{teacher}: {count}")
    else:
        lines.append("无")

    lines.append("")
    lines.append("[未命中任何关键词的教师]")
    no_match = sorted(
        [teacher for teacher, count in teacher_counts.items() if count == 0]
    )
    if no_match:
        lines.extend(no_match)
    else:
        lines.append("无")

    return "\n".join(lines) + "\n"


def write_summary(matches_by_teacher: dict[str, list[str]]) -> None:
    summary_text = build_summary(matches_by_teacher)
    SUMMARY_PATH.write_text(summary_text, encoding="utf-8")


def run_pipeline() -> dict[str, list[str]]:
    clean_all()
    matches_by_teacher = match_keywords()
    write_summary(matches_by_teacher)
    return matches_by_teacher


def list_keywords(matches_by_teacher: dict[str, list[str]]) -> None:
    keywords = load_keywords()
    counts = Counter()
    for matches in matches_by_teacher.values():
        for keyword in set(matches):
            counts[keyword] += 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    for keyword in keywords:
        if keyword not in counts:
            counts[keyword] = 0
    if not ordered:
        ordered = [(keyword, counts[keyword]) for keyword in keywords]
    for keyword, count in ordered:
        print(f"{keyword}: {count}")


def search_keyword(keyword: str, matches_by_teacher: dict[str, list[str]]) -> None:
    teachers = sorted(
        [teacher for teacher, matches in matches_by_teacher.items() if keyword in matches]
    )
    if teachers:
        for teacher in teachers:
            print(teacher)
    else:
        print("无匹配教师")


def main() -> None:
    parser = argparse.ArgumentParser(description="教师研究方向文本整理与统计分析")
    parser.add_argument("--list", action="store_true", help="列出关键词命中数量")
    parser.add_argument("--search", type=str, help="查询包含关键词的教师")
    args = parser.parse_args()

    matches_by_teacher = run_pipeline()

    if args.list:
        list_keywords(matches_by_teacher)
        return
    if args.search:
        search_keyword(args.search, matches_by_teacher)
        return


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
