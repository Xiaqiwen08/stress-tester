# -*- coding: utf-8 -*-
"""gen_string.py —— 读一行字符串

【适用题型】
    输入只有一行字符串的题：统计字符、回文、大小写转换、子串、字符串模拟……

【这道题的输入长什么样】
    aB 3!x
    就一行字符（末尾一个换行）。里面可能有大写、小写、数字、空格、特殊符号，
    也可能是空串，或者整行都是空格。

【一般只需要改这两行】
    第 41 行：LEN_MAX = 12 —— 最大长度。压力测试可以调到 200000。
    第 51 行：POOL_CN = "中文测试边界数据" —— 不想要中文/非 ASCII 字符，
                      就把这一行改成 POOL_CN = ""。

【其它可调项（一般不用动）】
    * make_char() 里各类字符的比例（字母数字 5 : 符号 2 : 空格 2 : 中文 1）  ← 改这里
    * EMPTY_P / BLANK_P / SINGLE_P / MAX_P / EDGE_SPACE_P —— 概率（%）       ← 改这里

【不要动的地方】
    下面代码里第 69、73、84、91 行附近标着「不要删」的那几处：
      1. 空串：只给一个换行（读到的是长度为 0 的字符串）
      2. 全是空格：有些程序栽在 input().split() 上
      3. 只有一个字符
      4. 顶到最大长度：LEN_MAX
      5. 字符串里保证出现 '0' 和 '-'（字符串题的"0 和负数"就是这两个字符）
      6. 随机地给首尾各加一个空格（栽在 strip 上的程序会现原形）
    为什么不能删：第 1、2 条喂的是"看起来像空、其实是数据"，第 6 条专治 strip 用错；
    这些正是你程序里 strip/split/切片边界最容易崩的地方。
    另外本模板不会在字符串中间插真正的换行（题目要求"读一行"），这一点也别改。

【数据规模】
    LEN_MAX 就是最大长度。默认 12，做压力测试可以调到 200000。
    中文/特殊符号混合时，注意目标程序自己的编码处理。
"""

import random   # 只有"直接运行本文件预览"时才用得到；main.py 会注入 rnd

# ============================== 参数 ==============================
LEN_MAX = 12        # ← 改这里：最大长度。压力测试可以调到 200000

EMPTY_P = 12        # ← 改这里：空串出现的概率（%）
BLANK_P = 8         # ← 改这里：整行都是空格的概率（%）
SINGLE_P = 12       # ← 改这里：只有一个字符的概率（%）
MAX_P = 12          # ← 改这里：顶到最大长度的概率（%）
EDGE_SPACE_P = 20   # ← 改这里：首尾加空格的概率（%）

POOL_EN = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
POOL_SYMBOL = "!@#$%^&*()_+-=[]{};:'\",.<>/?|~`"
POOL_CN = "中文测试边界数据"      # ← 改这里：不想要非 ASCII 字符就改成 ""


def make_char():
    """按比例吐一个字符：字母数字 5 : 特殊符号 2 : 空格 2 : 中文 1。"""
    kind = rnd.randint(1, 10)
    if kind <= 5:
        return rnd.choice(POOL_EN)
    if kind <= 7:
        return rnd.choice(POOL_SYMBOL)
    if kind <= 9:
        return " "
    return rnd.choice(POOL_CN) if POOL_CN else rnd.choice(POOL_EN)


def gen() -> str:
    roll = rnd.randint(1, 100)

    # —— 雷 1：空串（只给换行）。不要删 ——
    if roll <= EMPTY_P:
        return "\n"

    # —— 雷 2：整行都是空格。不要删 ——
    if roll <= EMPTY_P + BLANK_P:
        return " " * rnd.randint(1, 5) + "\n"

    if roll <= EMPTY_P + BLANK_P + SINGLE_P:
        s = rnd.choice(POOL_EN + POOL_SYMBOL)               # —— 雷 3：一个字符 ——
    elif roll <= EMPTY_P + BLANK_P + SINGLE_P + MAX_P:
        s = "".join(make_char() for _ in range(LEN_MAX))    # —— 雷 4：最大长度 ——
    else:
        s = "".join(make_char() for _ in range(rnd.randint(1, LEN_MAX)))

    # —— 雷 5：保证出现 '0' 和 '-'（在随机位置上换掉两个字符）。不要删 ——
    if len(s) >= 2:
        i = rnd.randrange(len(s))
        s = s[:i] + "0" + s[i + 1:]
        j = rnd.randrange(len(s))
        s = s[:j] + "-" + s[j + 1:]

    # —— 雷 6：首尾各加一个空格。不要删 ——
    if rnd.randint(1, 100) <= EDGE_SPACE_P:
        s = " " + s + " "

    return s + "\n"


if __name__ == "__main__":
    # 直接运行本文件预览数据时，main.py 不在，自己借一下已播种的全局 random
    random.seed(123)
    rnd = random
    for i in range(6):
        print("--- 第 {} 组 ---".format(i + 1))
        print(repr(gen()))
