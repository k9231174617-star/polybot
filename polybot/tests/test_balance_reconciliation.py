from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/polybot_test")

from bot.execution.orders import OrderExecutor


class BalanceReconciliationTests(unittest.TestCase):
    def test_extract_balance_value_prefers_balance_field(self) -> None:
        executor = OrderExecutor(dry_run=False)
        self.assertEqual(executor._extract_balance_value({"balance": "123.45", "allowance": 999}), 123.45)

    def test_extract_balance_value_handles_nested_payloads(self) -> None:
        executor = OrderExecutor(dry_run=False)
        self.assertEqual(executor._extract_balance_value({"data": {"result": {"available_balance": 88.5}}}), 88.5)


if __name__ == "__main__":
    unittest.main()
