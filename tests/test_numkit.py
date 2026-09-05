import unittest
import numkit


class TestNumkit(unittest.TestCase):
    def test_add(self):
        self.assertEqual(numkit.add(2, 3), 5)
    def test_safe_div_ok(self):
        self.assertEqual(numkit.safe_div(6, 3), 2.0)
    def test_safe_div_zero(self):
        with self.assertRaisesRegex(ValueError, "division by zero"):
            numkit.safe_div(1, 0)
    def test_fib(self):
        self.assertEqual([numkit.fib(n) for n in range(8)], [0, 1, 1, 2, 3, 5, 8, 13])
    def test_fib_negative(self):
        with self.assertRaisesRegex(ValueError, ">= 0"):
            numkit.fib(-3)
    def test_fact(self):
        self.assertEqual(numkit.fact(5), 120)
    def test_fact_negative(self):
        with self.assertRaisesRegex(ValueError, ">= 0"):
            numkit.fact(-1)
