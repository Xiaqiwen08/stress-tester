# -*- coding: utf-8 -*-
"""gen_query.py —— 先读 n 个数，再读 q 次询问

【适用题型】
    给一个数组，然后是若干次区间询问。区间求和 / 最值 / 计数、前缀和、线段树、
    树状数组、莫队……全部适用。

【生成的输入格式】
    第 1 行：n
    第 2 行：n 个整数
    第 3 行：q
    接下来 q 行：l r（表示询问区间 [l, r]，点编号从 1 开始，默认保证 l <= r）
    样例（n=3, q=2）：
        3
        0 100 -7
        2
        1 1
        1 3

【要改哪几行】
    * N_MAX / Q_MAX —— 数组长度、询问次数上限                          ← 改这里
    * VALUE_MIN / VALUE_MAX —— 数组元素范围                           ← 改这里
    * ALLOW_REVERSED_QUERY —— 要不要喂 l > r 这种非法区间               ← 改这里
    * 想改成别的询问形式（比如 l r k、单点修改 "1 i x"），就改 make_query()  ← 改这里

【故意塞进去的边界数据（不要删！）】
    1. 空输入：连 n 都没有（返回空字符串）
    2. n = 1 且 q = 1：最小规模
    3. 顶到最大规模：n = N_MAX，q = Q_MAX
    4. 数组里保证出现 0、负数和上界值
    5. 询问里保证出现 l == r（长度为 1 的区间）
    6. 询问里保证出现 l = 1, r = n（整个数组）
    7. 默认不会给 l > r 的非法区间；想要就打开 ALLOW_REVERSED_QUERY

【数据规模】
    N_MAX 管数组、Q_MAX 管询问次数。压力测试常见组合：
        N_MAX = 100000, Q_MAX = 100000
    询问次数多的时候，O(q*n) 的朴素写法会立刻超时，这正是你要抓的。
"""

import random   # 只有"直接运行本文件预览"时才用得到；main.py 会注入 rnd

# ============================== 参数 ==============================
N_MAX = 8           # ← 改这里：数组最长多少。压力测试可以调到 100000
Q_MAX = 5           # ← 改这里：最多询问几次。压力测试可以调到 100000
VALUE_MIN = -100    # ← 改这里：元素最小值（负数就来自这里）
VALUE_MAX = 100     # ← 改这里：元素最大值

ALLOW_REVERSED_QUERY = False   # ← 改这里：True = 允许生成 l > r 的非法区间
REVERSED_P = 20                # ← 改这里：非法区间占比（%），仅当上面为 True

EMPTY_P = 12        # ← 改这里：空输入出现的概率（%）
SINGLE_P = 12       # ← 改这里：n = 1 且 q = 1 的概率（%）
MAX_P = 12          # ← 改这里：顶到最大规模的概率（%）
SAME_LR_P = 20      # ← 改这里：l == r 的概率（%）
FULL_RANGE_P = 15   # ← 改这里：l = 1, r = n 的概率（%）


def make_value():
    """数组元素怎么取值。想生成只有 0/1 的数组就改这里。"""
    return rnd.randint(VALUE_MIN, VALUE_MAX)


def make_query(n: int) -> str:
    """一次询问。想加第三个参数（l r k）就在这里加。"""
    roll = rnd.randint(1, 100)

    # —— 雷：l == r，长度为 1 的区间。不要删 ——
    if roll <= SAME_LR_P:
        l = r = rnd.randint(1, n)
    # —— 雷：整个数组。不要删 ——
    elif roll <= SAME_LR_P + FULL_RANGE_P:
        l, r = 1, n
    else:
        l = rnd.randint(1, n)
        r = rnd.randint(l, n)

    # —— 雷（可选）：l > r 的非法区间。默认关着，打开后专治不判 l<=r 的程序 ——
    if ALLOW_REVERSED_QUERY and rnd.randint(1, 100) <= REVERSED_P:
        l, r = r, l

    return "{} {}".format(l, r)


def gen() -> str:
    roll = rnd.randint(1, 100)

    # —— 雷 1：空输入。不要删 ——
    if roll <= EMPTY_P:
        return ""

    if roll <= EMPTY_P + SINGLE_P:
        n, q = 1, 1                          # —— 雷 2：最小规模。不要删 ——
    elif roll <= EMPTY_P + SINGLE_P + MAX_P:
        n, q = N_MAX, Q_MAX                  # —— 雷 3：顶到最大规模。不要删 ——
    else:
        n, q = rnd.randint(1, N_MAX), rnd.randint(1, Q_MAX)

    arr = [make_value() for _ in range(n)]
    # —— 雷 4：数组里必须出现 0、负数和上界值。不要删 ——
    if n >= 2:
        arr[0] = 0
        arr[-1] = VALUE_MIN
    if n >= 3:
        arr[1] = VALUE_MAX

    lines = [str(n), " ".join(str(x) for x in arr), str(q)]
    lines.extend(make_query(n) for _ in range(q))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    # 直接运行本文件预览数据时，main.py 不在，自己借一下已播种的全局 random
    random.seed(123)
    rnd = random
    for i in range(6):
        print("--- 第 {} 组 ---".format(i + 1))
        print(gen(), end="")
