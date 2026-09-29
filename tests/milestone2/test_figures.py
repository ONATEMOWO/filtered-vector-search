import unittest

from analysis.generate_assignment_figures import latency_axis_upper_ms


class FigureAxisTests(unittest.TestCase):
    def test_later_larger_panel_cannot_be_clipped(self):
        runs = [
            {"conditions": {("exact", 50): {"median_latency_ns": 6000000}}},
            {"conditions": {("exact", 50): {"median_latency_ns": 40000000}}},
        ]
        self.assertAlmostEqual(latency_axis_upper_ms(runs), 43.2)
        self.assertEqual(latency_axis_upper_ms(runs), latency_axis_upper_ms(runs[::-1]))

    def test_zero_duration_still_has_positive_axis_range(self):
        self.assertGreater(latency_axis_upper_ms([
            {"conditions": {("exact", 50): {"median_latency_ns": 0}}}
        ]), 0)
