import random


def gen():
    """生成「已升序排列」的数组 + 目标和 S。
    - n >= 2：至少要两本，才有「挑两本」这回事
    - sorted(...)：保证题目「升序」的前提
    - S 的范围往上超一点：让「找得到」和「找不到(-1)」两种情况都被覆盖
    """
    n = random.randint(2, 10)
    a = sorted(random.randint(1, 20) for _ in range(n))
    s = random.randint(1, 2 * a[-1] + 5)
    return "{} {}\n{}\n".format(n, s, " ".join(map(str, a)))
