import unittest
from typing import final

from simple.config import parse_config_from_object


@final
class ConfigTests(unittest.TestCase):
    def test_method_1(self):
        o = {}
        self.assertRaises(ValueError, parse_config_from_object, o=o)
