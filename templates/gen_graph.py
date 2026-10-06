# -*- coding: utf-8 -*-
"""gen_graph.py —— 读 n 个点、m 条边（无向图）

【适用题型】
    第一行给 n m，接下来 m 行每行一条边。最短路、并查集、连通块、拓扑（改成有向即可）、
    最小生成树……所有图论题都从它开始。
    默认点编号从 1 开始（BASE = 1），边默认带权（HAS_WEIGHT = True）。

【生成的输入格式】
    第 1 行：n m
    接下来 m 行：u v w（无向边，w 是边权）；把 HAS_WEIGHT 改成 False 就变成 u v
    样例（n=4, m=3）：
        4 3
        1 2 0
        2 3 -50
        3 4 50

【要改哪几行】
    * HAS_WEIGHT —— 无权图改成 False（此时每条边只写 u v）              ← 改这里
    * ALLOW_SELF_LOOP / ALLOW_DUPLICATE —— 题目不禁自环/重边就打开       ← 改这里
    * BASE —— 点编号从 0 开始就改成 0                                   ← 改这里
    * N_MAX / M_MAX / W_MIN / W_MAX —— 规模、边权范围                   ← 改这里
    * EMPTY_P / SINGLE_P / ZERO_M_P / MAX_P / SHAPE_P —— 概率（%）        ← 改这里

    关于「0 和负数」：图的点编号是 1..n，天然没有 0 和负数。
    所以这两个雷放在**边权**上（HAS_WEIGHT = True 时）。如果你的题是无权图，
    把 HAS_WEIGHT 关掉，0/负数就不会出现——那时改用 n=1、m=0、自环、重边当雷。

【故意塞进去的边界数据（不要删！）】
    1. 空输入：连 n m 都没有（返回空字符串）
    2. n = 1 且 m = 0：只有一个孤点，一条边都没有
    3. m = 0：有若干个点但一条边都不给（图全是孤立点）
    4. 顶到最大规模：n = N_MAX，m = M_MAX
    5. 边权里保证出现 0、负数和上界值（带权模式下）
    6. 有时候生成链 / 星形这种"连通但不随机"的图（更接近真实数据）
    7. 默认**去重、不要自环**（符合大多数题的约定）；
       想主动喂自环/重边当雷，把 ALLOW_SELF_LOOP / ALLOW_DUPLICATE 打开

【数据规模】
    N_MAX 管点、M_MAX 管边。稀疏图（m ≈ n）一般是 N_MAX = 200000, M_MAX = 200000；
    稠密图注意 m 会被 n*(n-1)/2 自动截断，别指望生成出不存在的边。
"""

import random   # 只有"直接运行本文件预览"时才用得到；main.py 会注入 rnd

# ============================== 参数 ==============================
N_MAX = 6           # ← 改这里：最多几个点。压力测试可以调到 200000
M_MAX = 8           # ← 改这里：最多几条边。压力测试可以调到 200000
W_MIN = -50         # ← 改这里：边权最小值（负数就来自这里）
W_MAX = 50          # ← 改这里：边权最大值

HAS_WEIGHT = True   # ← 改这里：False = 无权图，每条边只写 u v
ALLOW_SELF_LOOP = False   # ← 改这里：True = 允许自环（u == v）
ALLOW_DUPLICATE = False   # ← 改这里：True = 允许重边
BASE = 1            # ← 改这里：点编号起点（0 或 1）

EMPTY_P = 10        # ← 改这里：空输入出现的概率（%）
SINGLE_P = 12       # ← 改这里：n = 1 且 m = 0 的概率（%）
ZERO_M_P = 10       # ← 改这里：m = 0 的概率（%）
MAX_P = 12          # ← 改这里：顶到最大规模的概率（%）
SHAPE_P = 30        # ← 改这里：生成链/星形（而不是纯随机图）的概率（%）


def make_edges(n: int, m: int, base_edges=()):
    """生成 m 条边。默认去重、不要自环，凑不够就返回实际凑到的条数。"""
    lo, hi = BASE, BASE + n - 1
    edges = []
    seen = set()

    def push(u: int, v: int) -> bool:
        if not ALLOW_SELF_LOOP and u == v:
            return False
        key = (min(u, v), max(u, v))
        if not ALLOW_DUPLICATE and key in seen:
            return False
        seen.add(key)
        edges.append((u, v))
        return True

    for u, v in base_edges:
        if len(edges) >= m:
            return edges
        push(u, v)

    tries, max_tries = 0, 100 * m + 500      # 加个上限，稠密图凑不满也不会死循环
    while len(edges) < m and tries < max_tries:
        tries += 1
        push(rnd.randint(lo, hi), rnd.randint(lo, hi))
    return edges


def gen() -> str:
    roll = rnd.randint(1, 100)

    # —— 雷 1：空输入。不要删 ——
    if roll <= EMPTY_P:
        return ""

    if roll <= EMPTY_P + SINGLE_P:
        n, m_wanted = 1, 0                   # —— 雷 2：孤点，没有边。不要删 ——
    elif roll <= EMPTY_P + SINGLE_P + ZERO_M_P:
        n = rnd.randint(1, N_MAX)
        m_wanted = 0                         # —— 雷 3：有边数但一条边都不给。不要删 ——
    elif roll <= EMPTY_P + SINGLE_P + ZERO_M_P + MAX_P:
        n, m_wanted = N_MAX, M_MAX           # —— 雷 4：顶到最大规模。不要删 ——
    else:
        n = rnd.randint(1, N_MAX)
        m_wanted = rnd.randint(1, M_MAX)

    # 不允许重边/自环时，边数不可能超过完全图的上限，这里自动截断
    if not ALLOW_DUPLICATE and not ALLOW_SELF_LOOP:
        m_wanted = min(m_wanted, n * (n - 1) // 2)

    # —— 雷 5：有时候给链 / 星形这种连通的规整图。不要删 ——
    base_edges = ()
    if n >= 2 and rnd.randint(1, 100) <= SHAPE_P:
        if rnd.randint(1, 100) <= 50:
            base_edges = [(BASE + i, BASE + i + 1) for i in range(n - 1)]     # 链
        else:
            base_edges = [(BASE, BASE + i) for i in range(1, n)]              # 星

    edges = make_edges(n, m_wanted, base_edges)
    m = len(edges)          # 用实际条数，保证 "n m" 和后面的边数一致

    weights = [rnd.randint(W_MIN, W_MAX) for _ in range(m)]
    # —— 雷 6：边权里必须出现 0、负数和上界值。不要删 ——
    if m >= 1:
        weights[0] = 0
        weights[-1] = W_MIN
    if m >= 2:
        weights[1] = W_MAX

    lines = ["{} {}".format(n, m)]
    for i, (u, v) in enumerate(edges):
        if HAS_WEIGHT:
            lines.append("{} {} {}".format(u, v, weights[i]))
        else:
            lines.append("{} {}".format(u, v))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    # 直接运行本文件预览数据时，main.py 不在，自己借一下已播种的全局 random
    random.seed(123)
    rnd = random
    for i in range(6):
        print("--- 第 {} 组 ---".format(i + 1))
        print(gen(), end="")
