# -*- coding: utf-8 -*-
"""配 gen_matrix.py 的最小目标程序：读 n m，再读 n*m 个整数。

空输入、0 0、1 1、只有一行、只有一列都要能正常退出。
"""
import sys


def main() -> None:
    tok = sys.stdin.read().split()
    if len(tok) < 2:                                # 空输入也要正常退出
        print("空输入")
        return
    n, m = int(tok[0]), int(tok[1])
    vals = [int(x) for x in tok[2:2 + n * m]]
    print("n =", n, "m =", m, "元素个数 =", len(vals), "和 =", sum(vals))


if __name__ == "__main__":
    main()
