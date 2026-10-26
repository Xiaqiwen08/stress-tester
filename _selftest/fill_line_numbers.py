# -*- coding: utf-8 -*-
"""一次性脚本：把 6 个模板头部里的 @@...@@ 行号占位符换成真实行号。

用法：python _selftest/fill_line_numbers.py
"""

from pathlib import Path

import re

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
# 每个模板的「一般只需要改这两行」说的是哪两个常量
CONSTANTS = {
    "gen_array.py": ["N_MAX", "VALUE_MIN"],
    "gen_string.py": ["LEN_MAX", "POOL_CN"],
    "gen_multi.py": ["T_MAX", "N_MAX"],
    "gen_matrix.py": ["N_MAX", "M_MAX"],
    "gen_graph.py": ["HAS_WEIGHT", "N_MAX"],
    "gen_query.py": ["N_MAX", "Q_MAX"],
}


def find_definition_line(lines, name):
    """找 `NAME = ...` 那一行（1 基行号），找不到返回 None。"""
    for index, line in enumerate(lines):
        if line.startswith(name + " ="):
            return index + 1
    return None


def find_docstring_end(lines):
    """返回模块 docstring 结束那行（内容就是三个引号）的 0 基下标。"""
    for index, line in enumerate(lines):
        if index > 0 and line.strip() == '"""':
            return index
    return -1


def main() -> int:
    for file_name, names in CONSTANTS.items():
        path = TEMPLATES / file_name
        text = path.read_text(encoding="utf-8")

        # 让脚本可以反复运行：先把上次填进去的数字还原成占位符
        text = re.sub(r"第 [\d、]+ 行附近标着「不要删」",
                      "第 @@RUI_LINES@@ 行附近标着「不要删」", text)
        for name in names:
            text = re.sub(rf"第 \d+ 行：{name} =", f"第 @@{name}@@ 行：{name} =", text)

        lines = text.split("\n")

        resolved = []
        for name in names:
            line_number = find_definition_line(lines, name)
            if line_number is None:
                print("!! 没找到", file_name, name)
                return 1
            resolved.append((name, line_number))
            text = text.replace(f"@@{name}@@", str(line_number))

        # 「不要删」那几处分布在哪些行。
        # 注意要跳过 docstring 本身——说明文字里也写着「不要删」这三个字。
        docstring_end = find_docstring_end(text.split("\n"))
        rui_lines = [str(index + 1)
                     for index, line in enumerate(text.split("\n"))
                     if index > docstring_end and "不要删" in line]
        if not rui_lines:
            print("!! 没找到「不要删」", file_name)
            return 1
        text = text.replace("@@RUI_LINES@@", "、".join(rui_lines))

        if "@@" in text:
            print("!! 还有没替换掉的占位符", file_name)
            return 1

        path.write_text(text, encoding="utf-8", newline="\n")
        pairs = "、".join(f"{name}=第 {number} 行" for name, number in resolved)
        print(f"{file_name}: {pairs}；雷在第 {'、'.join(rui_lines)} 行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
