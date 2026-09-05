# Task: numkit - a tiny Python package (v4pro loop smoke test)

This is a deliberately small, generic coding task. Its only purpose is to
exercise the v4pro loop:

    coder -> Ready -> REVIEW -> (FAIL -> fix -> Ready -> REVIEW)* -> MERGE

## The work

Create a small pure-Python package named `numkit` in the repository root of
your working directory:

- `numkit/__init__.py` exports four functions:
  - `add(a, b)` - integer addition
  - `safe_div(a, b)` - division; raises `ValueError` when `b == 0`
  - `fib(n)` - n-th Fibonacci number (fib(0)=0, fib(1)=1); raises `ValueError`
    for negative or non-integer n
  - `fact(n)` - n factorial (fact(0)=1); raises `ValueError` for negative or
    non-integer n
- `tests/test_numkit.py` with real unit tests (make `tests/` a package with
  an empty `__init__.py` so unittest discovery works) covering: normal
  inputs, the error inputs above (each error case asserts the exception type
  and message), and a couple of boundary values (e.g. fib(10), fact(5)).
- A `README.md` that names the functions, their error behavior, and the exact
  command to run the tests (`python3 -m unittest discover` is sufficient).
- A root `.gitignore` ignoring `__pycache__/` and `*.pyc`.
- The package must be importable from the repository root: `python3 -c
  "import numkit"` works.

## Acceptance criteria (what the reviewer will check)

1. All functions exist, are exported, and behave as specified, including
   every documented error case.
2. `python3 -m unittest discover` runs every test in the repository and
   passes with zero failures; the exact command, totals and exit code are
   recorded.
3. The repository is a clean git checkout: every file is committed, `git
   status` stays clean after a test run (the `.gitignore` keeps `__pycache__`
   out), no caches, credentials or generated junk.
4. Commit messages are clear; the README's run command matches reality.

## Delivery

Write your evidence (commands run, test totals and exit codes, git status)
into the artifacts directory named in the execution metadata block.