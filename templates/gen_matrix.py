# -*- coding: utf-8 -*-
"""gen_matrix.py —— 读 n 行 m 列的矩阵

【适用题型】
    第一行给 n m，接下来 n 行每行 m 个整数。矩阵/网格类题：转置、螺旋、前缀和、
    最大子矩阵、方向遍历……

【生成的输入格式】
    第 1 行：n m
    接下来 n 行，每行 m 个整数，空格分隔
    样例：
        2 3
        0 100 -7
        4 5 6

【要改哪几行】
    * N_MAX / M_MAX —— 行数、列数上限                                  ← 改这里
    * VALUE_MIN / VALUE_MAX —— 取值范围                               ← 改这里
    * EMPTY_P / SINGLE_P / ZERO_P / ROW_P / COL_P / MAX_P —— 概率（%）   ← 改这里

【故意塞进去的边界数据（不要删！）】
    1. 空输入：连 n m 都没有（返回空字符串）
    2. 0 0：空矩阵（有的程序会在这里除零或者越界）
    3. 1 1：只有一个元素
    4. 1 行 M 列 和 N 行 1 列：两个退化形状，最容易被"行列搞反"的程序坑
    5. 顶到最大规模：N_MAX 行 M_MAX 列
    6. 每个元素里都保证出现 0、负数和上界值（每行的第 1、2 个和最后 1 个）

【数据规模】
    N_MAX 管行、M_MAX 管列。总元素数 N_MAX * M_MAX 才是压力所在，例如：
        N_MAX = 1000, M_MAX = 1000     # 一百万个元素
"""

import random   # 只有"直接运行本文件预览"时才用得到；main.py 会注入 rnd

# ============================== 参数 ==============================
N_MAX = 4           # ← 改这里：最多几行。压力测试可以调到 1000
M_MAX = 5           # ← 改这里：最多几列。压力测试可以调到 1000
VALUE_MIN = -100    # ← 改这里：元素最小值（负数就来自这里）
VALUE_MAX = 100     # ← 改这里：元素最大值

EMPTY_P = 10        # ← 改这里：空输入出现的概率（%）
ZERO_P = 8          # ← 改这里：矩阵是 0 0 的概率（%）
SINGLE_P = 12       # ← 改这里：1 1 的概率（%）
ROW_P = 8           # ← 改这里：只有 1 行的概率（%）
COL_P = 8           # ← 改这里：只有 1 列的概率（%）
MAX_P = 12          # ← 改这里：顶到最大规模的概率（%）


def make_value():
    """一个元素怎么取值。想生成 0/1 矩阵就改成 rnd.randint(0, 1)。"""
    return rnd.randint(VALUE_MIN, VALUE_MAX)


def make_row(m: int) -> str:
    row = [make_value() for _ in range(m)]

    # —— 雷：每行都必须出现 0、负数和上界值。不要删 ——
    if m >= 2:
        row[0] = 0
        row[-1] = VALUE_MIN
    if m >= 3:
        row[1] = VALUE_MAX

    return " ".join(str(x) for x in row)


def gen() -> str:
    roll = rnd.randint(1, 100)

    # —— 雷 1：空输入。不要删 ——
    if roll <= EMPTY_P:
        return ""

    # —— 雷 2：0 0 空矩阵。不要删 ——
    if roll <= EMPTY_P + ZERO_P:
        n = m = 0
    # —— 雷 3：1 1。不要删 ——
    elif roll <= EMPTY_P + ZERO_P + SINGLE_P:
        n = m = 1
    # —— 雷 4：退化成一行。不要删 ——
    elif roll <= EMPTY_P + ZERO_P + SINGLE_P + ROW_P:
        n, m = 1, rnd.randint(1, M_MAX)
    # —— 雷 5：退化成列。不要删 ——
    elif roll <= EMPTY_P + ZERO_P + SINGLE_P + ROW_P + COL_P:
        n, m = rnd.randint(1, N_MAX), 1
    # —— 雷 6：顶到最大规模。不要删 ——
    elif roll <= EMPTY_P + ZERO_P + SINGLE_P + ROW_P + COL_P + MAX_P:
        n, m = N_MAX, M_MAX
    else:
        n, m = rnd.randint(1, N_MAX), rnd.randint(1, M_MAX)

    lines = ["{} {}".format(n, m)]
    for _ in range(n):
        lines.append(make_row(m))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    # 直接运行本文件预览数据时，main.py 不在，自己借一下已播种的全局 random
    random.seed(123)
    rnd = random
    for i in range(6):
        print("--- 第 {} 组 ---".format(i + 1))
        print(gen(), end="")
