# -*- coding: utf-8 -*-
"""配 gen_query.py 的最小目标程序：读 n、n 个数、q、q 行询问，逐个区间求和。

空输入、n=q=1、最大规模、l==r、l>r（打开 REVERSED 时）都要能正常退出。
"""
import sys


def main() -> None:
    tok = sys.stdin.read().split()
    if not tok:                                     # 空输入也要正常退出
        print("空输入")
        return
    n = int(tok[0])
    arr = [int(x) for x in tok[1:1 + n]]
    pos, q, total = 1 + n, int(tok[1 + n]), 0
    for _ in range(q):
        l, r = int(tok[pos]), int(tok[pos + 1]); pos += 2
        total += sum(arr[l - 1:r]) if l <= r else 0   # l > r 也不崩
    print("n =", n, "q =", q, "询问结果之和 =", total)


if __name__ == "__main__":
    main()
