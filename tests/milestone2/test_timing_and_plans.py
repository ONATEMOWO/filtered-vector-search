from __future__ import annotations

import unittest

from experiments.milestone2.database import HNSW_INDEX, timed_execute_fetch
from experiments.milestone2.plans import verify_plan_document


class FakeClock:
    def __init__(self, values: list[int], events: list[str]) -> None:
        self.values = iter(values)
        self.events = events

    def __call__(self) -> int:
        self.events.append("clock")
        return next(self.values)


class FakeCursor:
    def __init__(
        self,
        events: list[str],
        rows: list[tuple[int, float]] | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.events = events
        self.rows = rows or []
        self.error = error
        self.executed: tuple[str, object, bool] | None = None

    def execute(self, sql: str, parameters: object, *, prepare: bool) -> None:
        self.events.append("execute")
        self.executed = (sql, parameters, prepare)
        if self.error is not None:
            raise self.error

    def fetchall(self) -> list[tuple[int, float]]:
        self.events.append("fetchall")
        return self.rows


class TimingTests(unittest.TestCase):
    def test_timer_wraps_the_same_execute_and_complete_fetch(self) -> None:
        events: list[str] = []
        cursor = FakeCursor(events, rows=[(7, 1.25), (8, 2.5)])
        result = timed_execute_fetch(
            cursor,
            "SELECT test",
            ("vector",),
            clock=FakeClock([1_000, 1_175], events),
        )
        self.assertEqual(events, ["clock", "execute", "fetchall", "clock"])
        self.assertEqual(cursor.executed, ("SELECT test", ("vector",), True))
        self.assertEqual(result.rows, [(7, 1.25), (8, 2.5)])
        self.assertEqual(result.duration_ns, 175)
        self.assertIsNone(result.error_type)

    def test_failure_records_elapsed_time_without_fetching(self) -> None:
        events: list[str] = []
        cursor = FakeCursor(events, error=TimeoutError("too slow"))
        result = timed_execute_fetch(
            cursor,
            "SELECT test",
            (),
            clock=FakeClock([20, 55], events),
        )
        self.assertEqual(events, ["clock", "execute", "clock"])
        self.assertEqual(result.rows, [])
        self.assertEqual(result.duration_ns, 35)
        self.assertEqual(result.error_type, "TimeoutError")
        self.assertEqual(result.error_message, "too slow")

    def test_interrupts_are_not_swallowed(self) -> None:
        events: list[str] = []
        cursor = FakeCursor(events, error=KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            timed_execute_fetch(
                cursor,
                "SELECT test",
                (),
                clock=FakeClock([20, 55], events),
            )


def hnsw_settings(mode: str) -> dict[str, str]:
    return {
        "hnsw.ef_search": "40",
        "hnsw.iterative_scan": mode,
        "hnsw.max_scan_tuples": "20000",
        "hnsw.scan_mem_multiplier": "1",
        "work_mem": "64MB",
        "enable_seqscan": "off",
        "enable_bitmapscan": "off",
    }


def hnsw_document(threshold: int = 5) -> list[dict[str, object]]:
    return [
        {
            "Plan": {
                "Node Type": "Limit",
                "Actual Rows": 10,
                "Actual Loops": 1,
                "Plans": [
                    {
                        "Node Type": "Index Scan",
                        "Relation Name": "sift_hnsw",
                        "Index Name": HNSW_INDEX,
                        "Order By": "(embedding <-> '[0,0]'::vector)",
                        "Filter": f"(filter_bucket < {threshold})",
                        "Actual Rows": 10,
                        "Actual Loops": 1,
                        "Rows Removed by Filter": 40,
                    }
                ],
            },
            "Settings": {},
        }
    ]


def exact_document(node_type: str = "Seq Scan") -> list[dict[str, object]]:
    scan: dict[str, object] = {
        "Node Type": node_type,
        "Relation Name": "sift_exact",
        "Actual Rows": 50,
        "Actual Loops": 1,
    }
    if node_type in {"Index Scan", "Index Only Scan"}:
        scan["Index Name"] = "sift_exact_filter_bucket_idx"
    return [
        {
            "Plan": {
                "Node Type": "Limit",
                "Actual Rows": 10,
                "Actual Loops": 1,
                "Plans": [
                    {
                        "Node Type": "Sort",
                        "Sort Key": ["((embedding <-> '[0,0]'::vector))", "id"],
                        "Actual Rows": 10,
                        "Actual Loops": 1,
                        "Plans": [scan],
                    }
                ],
            }
        }
    ]


class PlanVerificationTests(unittest.TestCase):
    def test_standard_hnsw_plan_is_accepted(self) -> None:
        result = verify_plan_document(
            method="hnsw_standard",
            threshold=5,
            document=hnsw_document(),
            observed_settings=hnsw_settings("off"),
        )
        self.assertTrue(result["passed"], result["failures"])
        self.assertEqual(result["hnsw_scan_node_path"], "Plan.Plans[0]")
        self.assertEqual(result["rows_removed_by_filter"], 40)

    def test_strict_iterative_hnsw_plan_is_accepted(self) -> None:
        result = verify_plan_document(
            method="hnsw_iterative",
            threshold=5,
            document=hnsw_document(),
            observed_settings=hnsw_settings("strict_order"),
        )
        self.assertTrue(result["passed"], result["failures"])

    def test_valid_realistic_exact_plan_variants_are_accepted(self) -> None:
        for node_type in (
            "Seq Scan",
            "Parallel Seq Scan",
            "Index Scan",
            "Bitmap Heap Scan",
        ):
            with self.subTest(node_type=node_type):
                result = verify_plan_document(
                    method="exact",
                    threshold=5,
                    document=exact_document(node_type),
                    observed_settings={},
                )
                self.assertTrue(result["passed"], result["failures"])

    def test_hnsw_routing_failures_are_rejected(self) -> None:
        cases: list[tuple[str, list[dict[str, object]], dict[str, str]]] = []

        missing_index = hnsw_document()
        missing_index[0]["Plan"]["Plans"][0].pop("Index Name")  # type: ignore[index]
        cases.append(("missing index", missing_index, hnsw_settings("off")))

        missing_order = hnsw_document()
        missing_order[0]["Plan"]["Plans"][0].pop("Order By")  # type: ignore[index]
        cases.append(("missing order", missing_order, hnsw_settings("off")))

        misplaced_filter = hnsw_document()
        misplaced_filter[0]["Plan"]["Plans"][0].pop("Filter")  # type: ignore[index]
        misplaced_filter[0]["Plan"]["Filter"] = "(filter_bucket < 5)"  # type: ignore[index]
        cases.append(("misplaced filter", misplaced_filter, hnsw_settings("off")))

        wrong_mode = hnsw_settings("strict_order")
        cases.append(("wrong settings", hnsw_document(), wrong_mode))

        for label, document, settings in cases:
            with self.subTest(label=label):
                result = verify_plan_document(
                    method="hnsw_standard",
                    threshold=5,
                    document=document,
                    observed_settings=settings,
                )
                self.assertFalse(result["passed"])
                self.assertTrue(result["failures"])

    def test_exact_plan_using_hnsw_index_is_rejected(self) -> None:
        document = exact_document("Index Scan")
        document[0]["Plan"]["Plans"][0]["Plans"][0]["Index Name"] = HNSW_INDEX  # type: ignore[index]
        result = verify_plan_document(
            method="exact", threshold=5, document=document, observed_settings={}
        )
        self.assertFalse(result["passed"])
        self.assertIn("exact plan used a vector/HNSW index", result["failures"])

    def test_plan_without_actual_counts_is_rejected(self) -> None:
        document = hnsw_document()
        document[0]["Plan"].pop("Actual Rows")  # type: ignore[index]
        result = verify_plan_document(
            method="hnsw_standard",
            threshold=5,
            document=document,
            observed_settings=hnsw_settings("off"),
        )
        self.assertFalse(result["passed"])
        self.assertIn("plan lacks valid actual row/loop counts", result["failures"])

    def test_filter_threshold_must_match_exactly(self) -> None:
        result = verify_plan_document(
            method="hnsw_standard",
            threshold=5,
            document=hnsw_document(threshold=50),
            observed_settings=hnsw_settings("off"),
        )
        self.assertFalse(result["passed"])
        self.assertIn(
            "metadata predicate is not a filter on the HNSW scan", result["failures"]
        )

    def test_unknown_method_is_rejected(self) -> None:
        result = verify_plan_document(
            method="hnsw_typo",
            threshold=5,
            document=hnsw_document(),
            observed_settings=hnsw_settings("strict_order"),
        )
        self.assertFalse(result["passed"])
        self.assertIn("unknown method hnsw_typo", result["failures"])


if __name__ == "__main__":
    unittest.main()
