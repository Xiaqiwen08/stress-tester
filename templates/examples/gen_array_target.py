# -*- coding: utf-8 -*-
"""配 gen_array.py 的最小目标程序：读 n 和 n 个整数，打印个数/和/最值。

只用来验证「模板生成的输入合法、能被吃掉」。空输入、n=1、最大规模都要能正常退出。
"""
import sys


def main() -> None:
    data = sys.stdin.read().split()
    if not data:                                   # 空输入也要正常退出
        print("空输入")
        return
    n = int(data[0])
    nums = [int(x) for x in data[1:1 + n]]
    print("n =", n, "读到 =", len(nums), "和 =", sum(nums),
          "最小 =", min(nums) if nums else "-", "最大 =", max(nums) if nums else "-")


if __name__ == "__main__":
    main()
