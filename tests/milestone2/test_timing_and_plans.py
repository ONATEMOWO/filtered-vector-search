from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

from experiments.milestone2.database import (
    HNSW_INDEX,
    search_parameters,
    search_sql,
    timed_execute_fetch,
)
from experiments.milestone2.config import load_config
from experiments.milestone2.plans import audit_plan, verify_plan_document
from experiments.milestone2.runner import build_resource_projection, summarize_executions


ROOT = Path(__file__).resolve().parents[2]


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
    def test_every_search_binds_the_query_vector_once(self) -> None:
        vector = np.zeros(128, dtype=np.float32)
        for method in ("exact", "hnsw_standard", "hnsw_iterative"):
            with self.subTest(method=method):
                statement = search_sql(method, 5, 10)
                self.assertEqual(statement.count("%s"), 1)
                self.assertEqual(search_parameters(method, vector), (vector,))
        self.assertIn("ORDER BY distance LIMIT 10", search_sql("hnsw_standard", 5, 10))

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

    def test_summary_reduces_repetitions_per_query_first(self) -> None:
        rows = []
        for query_id, durations in ((1, (1, 101)), (2, (3, 5))):
            for duration in durations:
                rows.append(
                    {
                        "method": "exact",
                        "filter_threshold": 50,
                        "query_id": query_id,
                        "duration_ns": duration,
                        "error_type": None,
                        "canonical_recall_at_10": 1.0,
                        "tie_aware_recall_at_10": 1.0,
                        "returned_k": True,
                    }
                )
        summary = summarize_executions(rows)[0]
        self.assertEqual(summary["query_samples"], 2)
        self.assertEqual(summary["median_latency_ns"], 27)

    def test_resource_projection_covers_full_pipeline_and_artifacts(self) -> None:
        config = load_config(ROOT / "config" / "milestone2" / "qualification-100k.json")
        phase_names = (
            "source_scale_read_ns",
            "copy_exact_ns",
            "copy_hnsw_from_exact_ns",
            "exact_index_ns",
            "hnsw_build_ns",
            "vacuum_analyze_checkpoint_ns",
            "ground_truth_generation_ns",
            "ground_truth_determinism_reexecution_ns",
            "independent_ground_truth_validation_ns",
            "shared_buffer_reset_ns",
        )
        phases = {name: 100 for name in phase_names}
        phases.update(
            {"timed_workload_and_warmups_ns": 500, "total_before_final_artifacts_ns": 2_000}
        )
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "plans").mkdir()
            (run_dir / "executions.jsonl").write_bytes(b"x" * 100)
            (run_dir / "warmups.jsonl").write_bytes(b"x" * 50)
            (run_dir / "ground_truth.jsonl").write_bytes(b"x" * 200)
            (run_dir / "plans" / "one.json").write_bytes(b"x" * 30)
            projection = build_resource_projection(
                config,
                phases,
                [
                    {"duration_ns": 1_000, "error_type": None},
                    {"duration_ns": 2_000, "error_type": None},
                ],
                [{"relation_bytes": 100}],
                run_dir,
            )
        self.assertEqual(projection["eventual_timed_execution_count"], 120_000)
        self.assertEqual(projection["artifact_projection_counts"]["scale_rounds"], 8)
        self.assertGreater(projection["estimated_full_pipeline_seconds"], 0)
        self.assertGreater(projection["estimated_full_matrix_artifact_bytes"], 0)


def hnsw_settings(mode: str) -> dict[str, str]:
    return {
        **common_settings(),
        "hnsw.ef_search": "40",
        "hnsw.iterative_scan": mode,
        "hnsw.max_scan_tuples": "20000",
        "hnsw.scan_mem_multiplier": "1",
        "work_mem": "64MB",
        "enable_seqscan": "off",
        "enable_bitmapscan": "off",
    }


def common_settings() -> dict[str, str]:
    return {
        "jit": "off",
        "plan_cache_mode": "force_generic_plan",
        "statement_timeout": "2min",
    }


def exact_settings() -> dict[str, str]:
    return {
        **common_settings(),
        "enable_seqscan": "on",
        "enable_bitmapscan": "on",
        "enable_indexscan": "on",
        "enable_indexonlyscan": "on",
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
            fetched_result_count=10,
        )
        self.assertTrue(result["passed"], result["failures"])
        self.assertEqual(result["hnsw_scan_actual_rows"], 10)
        self.assertEqual(result["hnsw_scan_actual_loops"], 1)
        self.assertEqual(result["fetched_result_count"], 10)

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
                    observed_settings=exact_settings(),
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
            method="exact", threshold=5, document=document, observed_settings=exact_settings()
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

    def test_hnsw_scan_rows_must_match_root_rows(self) -> None:
        document = hnsw_document()
        document[0]["Plan"]["Plans"][0]["Actual Rows"] = 9  # type: ignore[index]
        result = verify_plan_document(
            method="hnsw_standard",
            threshold=5,
            document=document,
            observed_settings=hnsw_settings("off"),
        )
        self.assertFalse(result["passed"])
        self.assertIn(
            "HNSW scan actual rows 9 differ from root actual rows 10", result["failures"]
        )

    def test_hnsw_index_only_scan_is_rejected(self) -> None:
        document = hnsw_document()
        document[0]["Plan"]["Plans"][0]["Node Type"] = "Index Only Scan"  # type: ignore[index]
        result = verify_plan_document(
            method="hnsw_standard",
            threshold=5,
            document=document,
            observed_settings=hnsw_settings("off"),
        )
        self.assertFalse(result["passed"])
        self.assertIn("HNSW access is not the required Index Scan", result["failures"])

    def test_plan_rows_must_match_separately_fetched_result(self) -> None:
        result = verify_plan_document(
            method="hnsw_standard",
            threshold=5,
            document=hnsw_document(),
            observed_settings=hnsw_settings("off"),
            fetched_result_count=9,
        )
        self.assertFalse(result["passed"])
        self.assertIn(
            "root actual rows 10 differ from fetched result count 9", result["failures"]
        )
        self.assertIn(
            "HNSW scan actual rows 10 differ from fetched result count 9", result["failures"]
        )

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

    def test_common_settings_are_required_for_every_method(self) -> None:
        for method in ("exact", "hnsw_standard", "hnsw_iterative"):
            for name in common_settings():
                with self.subTest(method=method, setting=name):
                    settings = exact_settings() if method == "exact" else hnsw_settings(
                        "off" if method == "hnsw_standard" else "strict_order"
                    )
                    settings.pop(name)
                    result = verify_plan_document(
                        method=method,
                        threshold=5,
                        document=exact_document() if method == "exact" else hnsw_document(),
                        observed_settings=settings,
                    )
                    self.assertFalse(result["passed"])
                    self.assertTrue(any(name in failure for failure in result["failures"]))

    def test_exact_scan_paths_must_remain_enabled(self) -> None:
        for name in ("enable_seqscan", "enable_bitmapscan", "enable_indexscan", "enable_indexonlyscan"):
            with self.subTest(setting=name):
                settings = exact_settings()
                settings[name] = "off"
                result = verify_plan_document(
                    method="exact", threshold=5, document=exact_document(), observed_settings=settings
                )
                self.assertFalse(result["passed"])
                self.assertIn(f"session setting {name} expected on, got off", result["failures"])


class PreparedAuditCursor:
    def __init__(self, *, match_count: int = 1, generic_after: int = 3, custom_before: int = 0) -> None:
        self.calls: list[tuple[object, object, bool]] = []
        self.match_count = match_count
        self.generic_after = generic_after
        self.custom_before = custom_before

    def __enter__(self) -> "PreparedAuditCursor":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def execute(self, statement: object, parameters: object = None, *, prepare: bool) -> None:
        self.calls.append((statement, parameters, prepare))

    def fetchall(self) -> list[object]:
        if len(self.calls) == 1:
            return [(index, float(index)) for index in range(10)]
        return [(
            'prepared"name',
            search_sql("hnsw_standard", 5, 10).replace("%s", "$1"),
            "{vector}",
            2 if len(self.calls) == 2 else self.generic_after,
            self.custom_before,
        )] * self.match_count

    def fetchone(self) -> tuple[object]:
        return (hnsw_document(),)


class PreparedAuditConnection:
    def __init__(self, cursor: PreparedAuditCursor) -> None:
        self.test_cursor = cursor

    def cursor(self) -> PreparedAuditCursor:
        return self.test_cursor


class PreparedPlanAuditTests(unittest.TestCase):
    def audit(self, cursor: PreparedAuditCursor) -> tuple[object, object, dict[str, object]]:
        with patch("experiments.milestone2.plans.session_settings", return_value=hnsw_settings("off")):
            return audit_plan(
                PreparedAuditConnection(cursor),
                method="hnsw_standard", threshold=5, query_id=42,
                query_vector=np.zeros(128, dtype=np.float32), k=10, scale_rows=10_000,
            )

    def test_audit_explains_actual_prepared_query_with_safely_quoted_name(self) -> None:
        cursor = PreparedAuditCursor()
        _, _, record = self.audit(cursor)
        self.assertTrue(record["passed"], record["failures"])
        self.assertTrue(cursor.calls[0][2])
        self.assertEqual(cursor.calls[0][0], search_sql("hnsw_standard", 5, 10))
        self.assertEqual(cursor.calls[1][1], (search_sql("hnsw_standard", 5, 10).replace("%s", "$1"),))
        explain = cursor.calls[2][0].as_string()
        self.assertIn('EXECUTE "prepared""name" (', explain)
        self.assertNotIn("EXPLAIN SELECT", explain)
        self.assertFalse(cursor.calls[2][2])
        self.assertEqual(record["prepared_statement"]["generic_plans_after_explain"], 3)
        self.assertEqual(record["prepared_statement"]["statement"].count("$1"), 1)

    def test_missing_or_ambiguous_prepared_statement_is_rejected(self) -> None:
        for count in (0, 2):
            with self.subTest(count=count), self.assertRaisesRegex(AssertionError, "exactly one matching"):
                self.audit(PreparedAuditCursor(match_count=count))

    def test_custom_plan_or_unexecuted_generic_plan_is_rejected(self) -> None:
        with self.assertRaisesRegex(AssertionError, "exclusively use a generic"):
            self.audit(PreparedAuditCursor(custom_before=1))
        with self.assertRaisesRegex(AssertionError, "did not execute"):
            self.audit(PreparedAuditCursor(generic_after=2))


if __name__ == "__main__":
    unittest.main()
