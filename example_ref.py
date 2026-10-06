# -*- coding: utf-8 -*-
"""参考程序示例（对拍用）：和 example_target.py 读同一种输入，但算得又对又快。

example_target.py 故意留了两个 bug —— 最小值是 0 时除零崩溃、出现 3 个 999999 时睡 3 秒。
这个参考程序没有这些问题，正好拿来当"标准答案"：

    python main.py example_target.py --ref example_ref.py --seed 123

输入格式：第 1 行 n，第 2 行 n 个整数（空输入直接退出）。
"""

import sys


def main() -> None:
    tokens = sys.stdin.read().split()
    if not tokens:
        return
    n = int(tokens[0])
    nums = [int(x) for x in tokens[1:1 + n]]
    if not nums:
        return
    total = sum(nums)
    print("sum =", total)
    print("average =", total / n)
    # 最小值是 0 的时候 max/min 没有定义，这里照样给个答案，不崩
    print("max/min =", max(nums) / min(nums) if min(nums) != 0 else "未定义")


if __name__ == "__main__":
    main()
