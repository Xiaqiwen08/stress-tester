# -*- coding: utf-8 -*-
"""配 gen_graph.py 的最小目标程序：读 n m，再读 m 条边。

模板里 HAS_WEIGHT 默认是 True（每行 u v w）。要当无权图用，把下面的 WIDTH 改成 2，
同时把模板里的 HAS_WEIGHT 也改成 False。
空输入、n=1 m=0、m=0、最大规模都要能正常退出。
"""
import sys

WIDTH = 3                                           # ← 改这里：无权图改成 2


def main() -> None:
    tok = sys.stdin.read().split()
    if len(tok) < 2:                                # 空输入也要正常退出
        print("空输入")
        return
    n, m = int(tok[0]), int(tok[1])
    rest = [int(x) for x in tok[2:]]
    edges = [rest[i:i + WIDTH] for i in range(0, min(len(rest), m * WIDTH), WIDTH)]
    weights = [e[2] for e in edges] if WIDTH == 3 else []
    print("n =", n, "m =", m, "读到边数 =", len(edges),
          "最小边权 =", min(weights) if weights else "-")


if __name__ == "__main__":
    main()
