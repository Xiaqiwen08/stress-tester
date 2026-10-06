# -*- coding: utf-8 -*-
"""配 gen_string.py 的最小目标程序：读一行字符串，打印长度和大写形式。

空串、全是空格、一个字符、最大长度、带首尾空格都要能正常退出。
"""
import sys


def main() -> None:
    line = sys.stdin.readline().rstrip("\n")        # 只读一行，空串也接受
    print("长度 =", len(line))
    print("前 20 个大写 =", line.upper()[:20])


if __name__ == "__main__":
    main()
