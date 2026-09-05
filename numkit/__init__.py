def add(a, b):
    return a + b

def safe_div(a, b):
    if b == 0:
        raise ValueError("safe_div: division by zero")
    return a / b

def fib(n):
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValueError("fib: n must be an integer")
    if n < 0:
        raise ValueError("fib: n must be >= 0")
    if n == 0:
        return 0
    a, b = 0, 1
    for _ in range(n - 1):
        a, b = b, a + b
    return b if n >= 1 else 0

def fact(n):
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValueError("fact: n must be an integer")
    if n < 0:
        raise ValueError("fact: n must be >= 0")
    out = 1
    for k in range(2, n + 1):
        out *= k
    return out
