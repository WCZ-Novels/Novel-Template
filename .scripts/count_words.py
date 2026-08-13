#!/usr/bin/env python3
"""
字数统计脚本
统计根目录下的 .txt 文件，以及所有非点号开头目录中递归查找到的 .txt 文件字数，支持多种统计规则。

用法:
    python count_words.py <目录路径>
"""

import sys
import re
import os
import ctypes
from pathlib import Path


def _enable_windows_ansi() -> bool:
    # VS Code 终端通常支持 ANSI，优先放行
    if os.getenv("TERM_PROGRAM", "").lower() == "vscode":
        return True

    if os.name != "nt":
        return True
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)) == 0:
            return False
        new_mode = mode.value | 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        if kernel32.SetConsoleMode(handle, new_mode) == 0:
            return False
        return True
    except Exception:
        return False


ANSI_ENABLED = _enable_windows_ansi()


def _c(text: str, code: str) -> str:
    if not ANSI_ENABLED:
        return text
    return f"\033[{code}m{text}\033[0m"


# ── 统计规则 ────────────────────────────────────────────────────────────────

def count_all_chars(text: str) -> int:
    """规则1：所有字符（含空白、换行、标点）"""
    return len(text)


def count_non_whitespace(text: str) -> int:
    """规则2：去除空白字符（空格、换行、制表符等）后的字符数"""
    return len(re.sub(r'\s', '', text))


def count_chinese_chars(text: str) -> int:
    """规则3：仅统计汉字数量（CJK 统一汉字）"""
    return len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf\U00020000-\U0002a6df]', text))


def count_chinese_and_ascii_words(text: str) -> int:
    """规则4：汉字逐字计 + 英文按词计"""
    chinese = re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf\U00020000-\U0002a6df]', text)
    english_words = re.findall(r'[a-zA-Z]+', text)
    return len(chinese) + len(english_words)


def count_effective_chars(text: str) -> int:
    """规则5：有效字符数——去除空白及常见中英文标点（接近网文平台「字数」计法）"""
    text = re.sub(r'\s', '', text)
    text = re.sub(r'[，。！？；：""''（）【】《》〈〉、…——～·「」『』\u3000]', '', text)
    text = re.sub(r'[!"#$%&\'()*+,\-./:;<=>?@\[\\\]^_`{|}~]', '', text)
    return len(text)


RULES: list[tuple[str, object]] = [
    ("总字符数（含空白标点）",      count_all_chars),
    ("非空白字符数",                count_non_whitespace),
    ("汉字数",                      count_chinese_chars),
    ("汉字＋英文词数",              count_chinese_and_ascii_words),
    ("有效字符数（去空白标点）",    count_effective_chars),
]


# ── 主逻辑 ──────────────────────────────────────────────────────────────────

def collect_txt_files(root_path: Path) -> list[Path]:
    txt_files: list[Path] = sorted(root_path.glob("*.txt"))
    for child in sorted(root_path.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        txt_files.extend(sorted(child.rglob("*.txt")))
    return txt_files


def process_directory(dir_path: Path) -> None:
    txt_files = collect_txt_files(dir_path)

    if not txt_files:
        print(f"目录 '{dir_path}' 下未找到 .txt 文件。")
        return

    totals = [0] * len(RULES)
    file_results: list[tuple[str, list[int]]] = []

    for fpath in txt_files:
        try:
            text = fpath.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = fpath.read_text(encoding="gbk", errors="replace")

        counts = [rule_fn(text) for _, rule_fn in RULES]
        relative_name = str(fpath.relative_to(dir_path))
        file_results.append((relative_name, counts))
        for i, c in enumerate(counts):
            totals[i] += c

    rule_names = [name for name, _ in RULES]

    # 列宽计算
    name_w = max(max(len(r[0]) for r in file_results), len("文件名")) + 2
    num_w  = max(max(len(f"{t:,}") for t in totals), max(len(n) for n in rule_names)) + 2

    sep = "─" * (name_w + len(RULES) * (num_w + 2))
    col_sep = _c(" | ", "2;37")

    print(_c("== 字数统计 ==", "1;36"))
    print(f"{_c('目标目录', '1;34')}: {dir_path.resolve()}")
    print(f"{_c('文件数量', '1;34')}: {len(txt_files)}")
    print(_c("统计口径: 总字符 / 非空白 / 汉字 / 汉字+英文词 / 有效字符", "2;37"))
    print()

    metric_header_colors = ["1;35", "1;36", "1;32", "1;34", "1;31"]
    metric_value_colors = ["35", "36", "32", "34", "31"]

    header_cols = [_c(f"{'文件名':<{name_w}}", "1;34")]
    header_cols.extend(
        _c(f"{n:^{num_w}}", metric_header_colors[i % len(metric_header_colors)])
        for i, n in enumerate(rule_names)
    )
    print(col_sep.join(header_cols))
    print(_c(sep, "2;37"))

    for fname, counts in file_results:
        row_cols = [_c(f"{fname:<{name_w}}", "1;33")]
        row_cols.extend(
            _c(f"{c:>{num_w},}", metric_value_colors[i % len(metric_value_colors)])
            for i, c in enumerate(counts)
        )
        print(col_sep.join(row_cols))

    print(_c(sep, "2;37"))
    total_cols = [_c(f"{'合计':<{name_w}}", "1;36")]
    total_cols.extend(
        _c(f"{t:>{num_w},}", metric_header_colors[i % len(metric_header_colors)])
        for i, t in enumerate(totals)
    )
    print(col_sep.join(total_cols))
    print()


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python count_words.py <目录路径>")
        sys.exit(1)

    dir_path = Path(sys.argv[1]).expanduser().resolve()

    if not dir_path.exists():
        print(f"错误：路径 '{dir_path}' 不存在。")
        sys.exit(1)
    if not dir_path.is_dir():
        print(f"错误：'{dir_path}' 不是目录。")
        sys.exit(1)

    process_directory(dir_path)


if __name__ == "__main__":
    main()
