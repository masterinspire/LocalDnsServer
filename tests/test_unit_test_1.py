import unittest
from typing import final

from simple.stopwatch import Stopwatch


@final
class UnitTest1(unittest.TestCase):
    def test_method_1(self) -> None:
        pass

    def test_method_2(self) -> None:
        with Stopwatch() as stopwatch:
            pass

        with stopwatch:
            pass

        print(stopwatch.elapsed_milliseconds)


if __name__ == "__main__":
    unittest.main()
