# -*- coding: utf-8 -*-
"""配 gen_multi.py 的最小目标程序：一直读到 EOF，每组的格式是「k，然后 k 个数」。

关键是 k=0 的组不能让它转不出来，空输入也要正常退出。
"""
import sys


def main() -> None:
    tok = sys.stdin.read().split()
    pos = groups = total = 0
    while pos < len(tok):                           # 一直读到 EOF
        k = int(tok[pos]); pos += 1
        vals = [int(x) for x in tok[pos:pos + k]]; pos += k
        groups += 1
        total += sum(vals)
    print("组数 =", groups, "元素总数 =", total)


if __name__ == "__main__":
    main()
