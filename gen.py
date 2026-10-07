# -*- coding: utf-8 -*-
"""gen_array.py —— 读 n，再读 n 个整数

【适用题型】
    第一行给 n，第二行给 n 个整数。求和 / 排序 / 最值 / 前缀和 / 区间操作 / 双指针
    这类「一维数组」题，基本都用它。

【生成的输入格式】
    第 1 行：n
    第 2 行：n 个整数，空格分隔
    样例：
        3
        7 0 -4

【要改哪几行】
    * N_MAX / VALUE_MIN / VALUE_MAX —— 数据规模和取值范围              ← 改这里
    * EMPTY_P / SINGLE_P / MAX_P —— 三种歪数据的出现概率（%）           ← 改这里
    * make_value() —— 想换成浮点数、大整数就改它                        ← 改这里

【故意塞进去的边界数据（不要删！）】
    1. 空输入：连 n 都不给（返回空字符串）
    2. 单个元素：n = 1（数组只有一个元素时最容易越界）
    3. 顶到最大规模：n = N_MAX
    4. 每一组里都保证有 0：nums[0] = 0。
       n = 1 时同样成立（整个数组就是 [0]）——「只有一个元素而且是 0」是最容易
       同时踩到越界和除零的组合，所以这一组必须能生成出来；
       n >= 2 时最后一个元素还一定是负数 VALUE_MIN。
    5. 每一组里都保证有上界值：n >= 3 时 nums[1] = VALUE_MAX
    想让数据干净一点，就把标着「雷」的那几行注释掉（不建议，歪数据才是压力测试的价值）。

【数据规模】
    N_MAX 就是最大规模。默认 10（方便肉眼检查），做压力测试时直接调大，例如：
        N_MAX = 200000
    然后跑：
        python main.py templates/examples/gen_array_target.py --gen templates/gen_array.py --count 50 --timeout 3
"""

import random   # 只有"直接运行本文件预览"时才用得到；main.py 会注入 rnd

# ============================== 参数 ==============================
N_MAX = 10          # ← 改这里：最大 n。压力测试可以调到 200000
VALUE_MIN = -100    # ← 改这里：元素最小值（负数就来自这里）
VALUE_MAX = 100     # ← 改这里：元素最大值

EMPTY_P = 12        # ← 改这里：空输入出现的概率（%）
SINGLE_P = 12       # ← 改这里：只有一个元素出现的概率（%）
MAX_P = 12          # ← 改这里：顶到最大规模出现的概率（%）


def make_value():
    """一个元素怎么取值。想生成浮点数就改成 round(rnd.uniform(VALUE_MIN, VALUE_MAX), 2)。"""
    return rnd.randint(VALUE_MIN, VALUE_MAX)


def gen() -> str:
    roll = rnd.randint(1, 100)

    # —— 雷 1：空输入，连 n 都没有。不要删 ——
    if roll <= EMPTY_P:
        return ""

    if roll <= EMPTY_P + SINGLE_P:
        n = 1                                   # —— 雷 2：只有一个元素。不要删 ——
    elif roll <= EMPTY_P + SINGLE_P + MAX_P:
        n = N_MAX                               # —— 雷 3：顶到最大规模。不要删 ——
    else:
        n = rnd.randint(1, N_MAX)

    nums = [make_value() for _ in range(n)]

    # —— 雷 4：值里必须出现 0 和负数；雷 5：必须出现上界值。不要删 ——
    if n >= 1:
        nums[0] = 0            # n = 1 时也必须是 0：单个 0 最容易同时暴露越界和除零
    if n >= 2:
        nums[-1] = VALUE_MIN
    if n >= 3:
        nums[1] = VALUE_MAX

    return "\n".join([str(n), " ".join(str(x) for x in nums)]) + "\n"


if __name__ == "__main__":
    # 直接运行本文件预览数据时，main.py 不在，自己借一下已播种的全局 random
    random.seed(123)
    rnd = random
    for i in range(6):
        print("--- 第 {} 组 ---".format(i + 1))
        print(gen(), end="")
