#!/usr/bin/env python3
"""
敏感词过滤脚本（Aho-Corasick）

扫描范围：
1) 根目录下所有 .txt
2) 所有非点号开头子目录中递归查找的 .txt

默认使用 .data/tencent-sensitive-words/sensitive_words_lines.txt 作为词库。

用法示例：
    python filter_sensitive_words.py <目录路径>
    python filter_sensitive_words.py <目录路径> --include-single-char
"""

from __future__ import annotations

import argparse
import ctypes
import os
import sys
import time
from bisect import bisect_right
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import quote


DEFAULT_WORDS_REL_PATH = Path(".data/tencent-sensitive-words/sensitive_words_lines.txt")
DEFAULT_WHITELIST_REL_PATH = Path(".data/sensitive_words_whitelist.dic")
DEFAULT_EXTRA_BLACKLIST_REL_PATH = Path(".data/sensitive_words_extra_blacklist.dic")


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


def set_color_mode(mode: str) -> None:
    global ANSI_ENABLED
    if mode == "always":
        # 跨平台：Windows 需要尝试开启 ANSI，其他系统可直接使用
        ANSI_ENABLED = _enable_windows_ansi() if os.name == "nt" else True
    elif mode == "never":
        ANSI_ENABLED = False
    else:
        ANSI_ENABLED = _enable_windows_ansi()


def _c(text: str, code: str) -> str:
    if not ANSI_ENABLED:
        return text
    return f"\033[{code}m{text}\033[0m"


def _link(label: str, url: str) -> str:
    # 终端支持 OSC 8 时显示短文本并保持可点击。
    if ANSI_ENABLED:
        return f"\033]8;;{url}\033\\{label}\033]8;;\033\\"
    return f"{label} -> {url}"


def _render_progress(done: int, total: int, elapsed: float, width: int = 28) -> str:
    if total <= 0:
        total = 1
    ratio = done / total
    filled = int(width * ratio)
    bar = "█" * filled + "-" * (width - filled)
    percent = int(ratio * 100)
    speed = done / elapsed if elapsed > 0 else 0.0
    return f"{percent:3d}%|{bar}| {done}/{total} [{elapsed:5.1f}s, {speed:4.1f} file/s]"


def _print_progress(done: int, total: int, elapsed: float, force: bool = False) -> None:
    line = _render_progress(done, total, elapsed)
    # TTY 下实时覆盖同一行；非 TTY 下仅在 force 时输出一次最终进度。
    if not sys.stdout.isatty() and not force:
        return
    if sys.stdout.isatty() and not force:
        sys.stdout.write("\r" + _c(line, "1;32"))
        sys.stdout.flush()
        return
    print(_c(line, "1;32"))


def _clear_progress_line() -> None:
    # 清除当前进度条行（仅在交互终端可见）
    if not sys.stdout.isatty():
        return
    sys.stdout.write("\r\033[2K\r")
    sys.stdout.flush()


def _highlight_context(context: str, word: str) -> str:
    # 上下文默认白色，命中词使用紫色底高亮（文字仍为白色）
    if not ANSI_ENABLED or not word:
        return context

    parts = context.split(word)
    if len(parts) == 1:
        return _c(context, "37")

    warning = _c(word, "1;37;45")
    out = ""
    for i, part in enumerate(parts):
        out += _c(part, "37")
        if i < len(parts) - 1:
            out += warning
    return out


@dataclass
class ACNode:
    children: Dict[str, "ACNode"] = field(default_factory=dict)
    fail: "ACNode | None" = None
    outputs: List[int] = field(default_factory=list)


class AhoCorasick:
    def __init__(self, words: List[str]) -> None:
        self.root = ACNode()
        self._build_trie(words)
        self._build_fail_links()

    def _build_trie(self, words: List[str]) -> None:
        for word in words:
            node = self.root
            for ch in word:
                node = node.children.setdefault(ch, ACNode())
            node.outputs.append(len(word))

    def _build_fail_links(self) -> None:
        self.root.fail = self.root
        queue: deque[ACNode] = deque()

        for child in self.root.children.values():
            child.fail = self.root
            queue.append(child)

        while queue:
            current = queue.popleft()
            for ch, nxt in current.children.items():
                queue.append(nxt)
                f = current.fail
                while f is not None and f is not self.root and ch not in f.children:
                    f = f.fail
                if f is not None and ch in f.children:
                    nxt.fail = f.children[ch]
                else:
                    nxt.fail = self.root
                if nxt.fail.outputs:
                    nxt.outputs.extend(nxt.fail.outputs)

    def find_matches(self, text: str) -> List[Tuple[int, int]]:
        """返回所有匹配区间 [start, end)"""
        matches: List[Tuple[int, int]] = []
        node = self.root

        for i, ch in enumerate(text):
            while node is not self.root and ch not in node.children:
                node = node.fail if node.fail is not None else self.root
            if ch in node.children:
                node = node.children[ch]
            else:
                node = self.root

            if node.outputs:
                for length in node.outputs:
                    start = i - length + 1
                    if start >= 0:
                        matches.append((start, i + 1))

        return matches


@dataclass
class MatchDetail:
    word: str
    start: int
    end: int
    line: int
    column: int
    context: str


def load_whitelist(whitelist_file: Path) -> set[str]:
    if not whitelist_file.exists():
        return set()

    white: set[str] = set()
    for line in whitelist_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        word = line.strip()
        if not word or word.startswith("#"):
            continue
        white.add(word)
    return white


def load_extra_blacklist(extra_blacklist_file: Path) -> List[str]:
    if not extra_blacklist_file.exists():
        return []

    words: List[str] = []
    seen: set[str] = set()
    for line in extra_blacklist_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        word = line.strip()
        if not word or word.startswith("#"):
            continue
        if word in seen:
            continue
        seen.add(word)
        words.append(word)
    return words


def load_words(
    words_file: Path,
    whitelist: set[str],
    extra_blacklist: List[str],
    include_single_char: bool = False,
) -> List[str]:
    if not words_file.exists():
        raise FileNotFoundError(f"敏感词文件不存在: {words_file}")

    words: List[str] = []
    seen = set()

    for line in words_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        word = line.strip()
        if not word or word in seen:
            continue
        if word in whitelist:
            continue
        if not include_single_char and len(word) == 1:
            continue
        seen.add(word)
        words.append(word)

    if not words:
        raise ValueError(f"敏感词文件为空或无有效词条: {words_file}")

    # 补充黑名单后置追加：可覆盖白名单排除（用于强制补充敏感词）
    for word in extra_blacklist:
        if word in seen:
            continue
        seen.add(word)
        words.append(word)

    return words


def collect_txt_files(root_path: Path) -> List[Path]:
    txt_files: List[Path] = sorted(root_path.glob("*.txt"))
    for child in sorted(root_path.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        txt_files.extend(sorted(child.rglob("*.txt")))
    return txt_files


def detect_project_root(script_path: Path) -> Path:
    # 约定脚本放在 .scripts 下，其父目录即项目根目录
    return script_path.parent.parent


def read_text_with_fallback(file_path: Path) -> str:
    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return file_path.read_text(encoding="gbk", errors="replace")


def build_match_details(text: str, matches: List[Tuple[int, int]]) -> List[MatchDetail]:
    if not matches:
        return []

    line_starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            line_starts.append(i + 1)

    details: List[MatchDetail] = []
    for start, end in matches:
        if start < 0 or end > len(text) or start >= end:
            continue

        line_idx = bisect_right(line_starts, start) - 1
        line_no = line_idx + 1
        col_no = start - line_starts[line_idx] + 1

        word = text[start:end]
        context_start = max(0, start - 12)
        context_end = min(len(text), end + 12)
        context = text[context_start:context_end].replace("\n", "\\n")
        details.append(
            MatchDetail(
                word=word,
                start=start,
                end=end,
                line=line_no,
                column=col_no,
                context=context,
            )
        )

    return details


def process_file(ac: AhoCorasick, file_path: Path) -> Tuple[int, List[MatchDetail]]:
    text = read_text_with_fallback(file_path)

    matches = ac.find_matches(text)
    details = build_match_details(text, matches)
    return len(matches), details


@dataclass
class FileScanResult:
    rel_posix: str
    rel_native: str
    match_count: int
    details: List[MatchDetail]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="过滤目录内 .txt 文件中的敏感词，并输出命中详情")
    parser.add_argument("directory", type=str, help="目标目录路径")
    parser.add_argument(
        "--include-single-char",
        action="store_true",
        help="包含单字敏感词（默认忽略单字词）",
    )
    parser.add_argument(
        "--color",
        choices=["auto", "always", "never"],
        default="always",
        help="颜色模式：always(默认)/auto/never",
    )
    parser.add_argument(
        "--vscode-problems",
        action="store_true",
        help="额外输出 VS Code 问题匹配行（file:line:start-end: error: message）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    set_color_mode(args.color)

    root = Path(args.directory).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"错误：目录不存在或不是目录: {root}")

    script_file = Path(__file__).resolve()
    project_root = detect_project_root(script_file)

    words_file = project_root / DEFAULT_WORDS_REL_PATH
    whitelist_file = project_root / DEFAULT_WHITELIST_REL_PATH
    extra_blacklist_file = project_root / DEFAULT_EXTRA_BLACKLIST_REL_PATH

    whitelist = load_whitelist(whitelist_file)
    extra_blacklist = load_extra_blacklist(extra_blacklist_file)

    words = load_words(
        words_file,
        whitelist=whitelist,
        extra_blacklist=extra_blacklist,
        include_single_char=args.include_single_char,
    )
    ac = AhoCorasick(words)

    txt_files = collect_txt_files(root)
    if not txt_files:
        print(f"目录下未找到 .txt 文件: {root}")
        return

    total_matches = 0

    print(_c("== 敏感词扫描 ==", "1;36"))
    print(f"{_c('目标目录', '1;34')}: {root}")
    print(f"{_c('文件数量', '1;34')}: {len(txt_files)}")
    print(f"{_c('单字词', '1;34')}: {'包含' if args.include_single_char else '忽略'}")
    print(f"{_c('白名单词数', '1;34')}: {len(whitelist)}")
    print(f"{_c('补充黑名单词数', '1;34')}: {len(extra_blacklist)}")
    print(_c("输出: 单行三列（默认色=跳转, 紫字=敏感词, 白=上下文, 紫底白字=上下文命中词）", "2;37"))
    print()

    no_hit_files: List[str] = []
    scan_results: List[FileScanResult] = []
    start_ts = time.perf_counter()
    _print_progress(0, len(txt_files), 0.0)

    for idx, file_path in enumerate(txt_files, start=1):
        match_count, details = process_file(ac, file_path)
        total_matches += match_count

        # 每处理完一个文件都刷新总进度
        elapsed = time.perf_counter() - start_ts
        _print_progress(idx, len(txt_files), elapsed)

        rel = file_path.relative_to(root)
        scan_results.append(
            FileScanResult(
                rel_posix=rel.as_posix(),
                rel_native=str(rel),
                match_count=match_count,
                details=details,
            )
        )

    # 扫描完成后隐藏进度条
    _clear_progress_line()

    for item in scan_results:
        file_title = f"{item.rel_posix} | 匹配次数={item.match_count}"
        if item.match_count > 0:
            print(_c(file_title, "1;33"))
            for d in item.details:
                abs_posix = (root / item.rel_native).resolve().as_posix()
                jump_uri = f"vscode://file/{quote(abs_posix, safe='/:')}:{d.line}:{d.column}"
                jump_label = f".\\{item.rel_native}({d.line},{d.column})"
                word_chip = _c(d.word, "1;35")
                print(
                    f"{_link(jump_label, jump_uri)}"
                    f" {_c('|', '2;37')} "
                    f"{word_chip}"
                    f" {_c('|', '2;37')} "
                    f"{_highlight_context(d.context, d.word)}"
                )
                if args.vscode_problems:
                    # VS Code 的 endColumn 采用结束后一列，需使用开区间尾。
                    end_col = d.column + max(len(d.word), 1)
                    print(
                        f"{item.rel_posix}:{d.line}:{d.column}-{end_col}: error: "
                        f"敏感词命中「{d.word}」 上下文: {d.context}"
                    )
            print()
        else:
            no_hit_files.append(item.rel_posix)

    if no_hit_files:
        print(_c("未命中文件", "2;37") + f" ({len(no_hit_files)}): " + _c(", ".join(no_hit_files), "2;37"))

    if total_matches == 0:
        print("未命中敏感词")


if __name__ == "__main__":
    main()
