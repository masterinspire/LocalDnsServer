import unittest
from typing import final

from simple.parse_rules import parse_cloaking_rules, parse_line


@final
class ParseLineTests(unittest.TestCase):
    def test_method_1(self):
        text = """

123 #
123   # 123
# 1234
1234        # 123
12345

"""

        result = parse_line(text)
        self.assertListEqual(result, sorted(["1234", "123", "12345"]))

    def test_method_5(self):
        text = """
        www.abc.com     123.1.1.1
        www.abc.com     abc.com
        www.abc.com     www.abc.com
        www.abc.com     *.abc.com
        WWW.ABC.COM     ABC.COM
        WWW.ABC.COM     abc.com
        """
        result = parse_cloaking_rules("default", text)
        self.assertTrue(len(result) == 2)


if __name__ == "__main__":
    unittest.main()
