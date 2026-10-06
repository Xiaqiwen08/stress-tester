# -*- coding: utf-8 -*-
"""被测试程序示例：故意留了两个 bug，用来演示压力测试器

输入格式（和 gen.py 约定的一致）
    第 1 行：整数 n
    第 2 行：n 个整数，空格分隔

输出
    sum / average / max/min

故意留下的两个问题
    1. 只要数据里最小值是 0，max/min 就会 ZeroDivisionError
       -> 压力测试器记为「崩溃」，并保存输入和报错；
    2. 数据里出现 3 个 999999 时会 sleep 3 秒
       -> 压力测试器记为「超时」（超过默认的 1 秒）。

跑法：
    python main.py example_target.py --seed 123
"""

import sys
import time


def main() -> None:
    tokens = sys.stdin.read().split()
    if not tokens:
        print("没有读到任何输入", file=sys.stderr)
        return

    n = int(tokens[0])
    nums = [int(x) for x in tokens[1:1 + n]]

    if nums.count(999999) >= 3:      # bug 2：慢，用来演示「超时」
        time.sleep(3)

    print("sum =", sum(nums))
    print("average =", sum(nums) / n)
    print("max/min =", max(nums) / min(nums))   # bug 1：min 为 0 时崩


if __name__ == "__main__":
    main()
