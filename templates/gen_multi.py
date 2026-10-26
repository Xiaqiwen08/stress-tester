# -*- coding: utf-8 -*-
"""gen_multi.py —— 多组数据，一直读到 EOF

【适用题型】
    "不知道有多少组"的题：给若干个数据块，每组都是一小段输入，一直处理到文件结尾。
    典型是「多组测试用例」的入门题。
    注意：本模板约定 EOF 是唯一的结束标志，不用 0 当结束符；如果你那题用 0 结束，
    就把 ZERO_P 调成 0、并把"整组 n=0"当成结束符处理。

【这道题的输入长什么样】
    2
    5 0
    1
    -7
    0
    组与组直接连着写，一直写到底（EOF 结束）。每组都是两行：第 1 行 k，第 2 行 k 个整数。
    上面这个样例是 3 组，k 分别是 2 / 1 / 0。

【一般只需要改这两行】
    第 47 行：T_MAX = 4 —— 最多几组。压力测试可以调到 100000。
    第 48 行：N_MAX = 8 —— 每组最多几个元素。

【其它可调项（一般不用动）】
    * VALUE_MIN / VALUE_MAX —— 取值范围                                 ← 改这里
    * EMPTY_P / SINGLE_P / MAX_P / ZERO_P —— 各种歪数据的概率（%）        ← 改这里

【不要动的地方】
    下面代码里第 69、82、97 行附近标着「不要删」的那几处：
      1. 空输入：一组都没有（返回空字符串）
      2. 只有一组、而且只有一个元素
      3. 顶到最大规模：T_MAX 组，每组 N_MAX 个元素
      4. 某一组的 k = 0（小心死循环！很多"读 k 再读 k 个数"的循环会在这里转不出来）
      5. 每组里都保证有 0 和负数：nums[0] = 0，nums[-1] = VALUE_MIN
      6. 每组里都保证有上界值：nums[1] = VALUE_MAX
    为什么不能删：第 4 条是这类题最经典的死循环来源（while 循环里读 k=0 会原地打转）；
    第 1 条测"根本没有输入"时你的程序会不会直接崩。删了就测不到了。

【数据规模】
    T_MAX 管组数、N_MAX 管每组的元素数。做压力测试可以调成
        T_MAX = 100000, N_MAX = 100
    总元素数 = T_MAX * N_MAX 是真正压时间的地方，调之前先想清楚目标程序的时间复杂度。
"""

import random   # 只有"直接运行本文件预览"时才用得到；main.py 会注入 rnd

# ============================== 参数 ==============================
T_MAX = 4           # ← 改这里：最多几组。压力测试可以调到 100000
N_MAX = 8           # ← 改这里：每组最多几个元素
VALUE_MIN = -100    # ← 改这里：元素最小值（负数就来自这里）
VALUE_MAX = 100     # ← 改这里：元素最大值

EMPTY_P = 12        # ← 改这里：一组都没有的概率（%）
SINGLE_P = 12       # ← 改这里：只有一组且只有一个元素的概率（%）
MAX_P = 12          # ← 改这里：顶到最大规模的概率（%）
ZERO_P = 15         # ← 改这里：某一组 k = 0 的概率（%）

GUARD = 200         # 防止 T_MAX 被调得极大时一次性拼出天量字符串（一般不用动）


def make_value():
    """一个元素怎么取值。想换成浮点数就改这里。"""
    return rnd.randint(VALUE_MIN, VALUE_MAX)


def make_group(k: int) -> str:
    """拼一组：先 k，再 k 个数。"""
    nums = [make_value() for _ in range(k)]

    # —— 雷：每组里都必须出现 0、负数和上界值。不要删 ——
    if k >= 2:
        nums[0] = 0
        nums[-1] = VALUE_MIN
    if k >= 3:
        nums[1] = VALUE_MAX

    return "\n".join([str(k), " ".join(str(x) for x in nums)]) + "\n"


def gen() -> str:
    roll = rnd.randint(1, 100)

    # —— 雷 1：空输入，一组都没有。不要删 ——
    if roll <= EMPTY_P:
        return ""

    if roll <= EMPTY_P + SINGLE_P:
        groups, size = 1, 1                      # —— 雷 2：一组一个元素 ——
    elif roll <= EMPTY_P + SINGLE_P + MAX_P:
        groups, size = T_MAX, N_MAX              # —— 雷 3：顶到最大规模 ——
    else:
        groups = rnd.randint(1, T_MAX)
        size = rnd.randint(1, N_MAX)

    parts = []
    for _ in range(min(groups, GUARD)):
        k = size
        # —— 雷 4：偶尔来一组 k = 0。不要删 ——
        if rnd.randint(1, 100) <= ZERO_P:
            k = 0
        parts.append(make_group(k))

    return "".join(parts)


if __name__ == "__main__":
    # 直接运行本文件预览数据时，main.py 不在，自己借一下已播种的全局 random
    random.seed(123)
    rnd = random
    for i in range(6):
        print("--- 第 {} 组 ---".format(i + 1))
        print(gen(), end="")
