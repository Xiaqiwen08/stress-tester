# -*- coding: utf-8 -*-
"""数据生成规则（示例，可以直接用）

规则只有两条
------------
1. 本文件里必须有一个 gen() 函数；
2. 每次调用 gen() 返回一个字符串，这个字符串就是喂给被测试程序的一整组输入
   （压力测试器会把它整段写进被测试程序的 stdin，然后关掉 stdin）。

怎么做才能被 --seed 复现
------------------------
压力测试器加载本文件之后，会往这个模块里注入两个名字：

    SEED : 本次运行使用的随机种子（整数）
    rnd  : random.Random(SEED)，一个已经播好种的独立随机数发生器

另外，压力测试器还会在导入本文件之前对全局 random 模块播种，
所以下面两种写法都是可复现的：

    n = random.randint(1, 8)      # 用全局 random
    n = rnd.randint(1, 8)         # 用注入的 rnd

不要自己再定义 SEED / rnd，也不要用没播种的随机源
（random.Random()、os.urandom()、time.time() 等），
否则给了 --seed 也跑不出一样的数据。

本示例生成的数据格式（对应 example_target.py）
---------------------------------------------
    第 1 行：整数 n
    第 2 行：n 个整数，用空格分隔
"""

import random

# 每个数的候选取值：故意混进 0（会让 example_target.py 除以零崩溃）
# 和 999999（出现 3 个就会让 example_target.py 变慢，从而超时）。
NUMBERS = [0, 1, 2, 3, 5, 7, -4, 999999]


def gen() -> str:
    """生成一组完整的输入，返回字符串。"""
    n = random.randint(1, 8)
    nums = [random.choice(NUMBERS) for _ in range(n)]
    return "{}\n{}\n".format(n, " ".join(str(x) for x in nums))


# 自测用：直接运行本文件，可以看看生成的数据长什么样。
#     python gen.py
if __name__ == "__main__":
    random.seed(123)
    for i in range(5):
        print(f"--- 第 {i + 1} 组 ---")
        print(gen(), end="")
