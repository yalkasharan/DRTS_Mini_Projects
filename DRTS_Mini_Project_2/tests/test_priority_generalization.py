import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANALYTICAL_ROOT = PROJECT_ROOT / "analytical"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(ANALYTICAL_ROOT))

from model import CBSConfig
from tsn_parser import assign_priority_classes, load_routes, load_streams, load_topology
from wcrt_analysis import analyze


class PriorityGeneralizationTests(unittest.TestCase):
    def test_two_cbs_class_case_matches_reference_values(self) -> None:
        case_dir = PROJECT_ROOT / "Required Files" / "test_case_1"
        _, links = load_topology(str(case_dir / "topology.json"))
        streams = load_streams(str(case_dir / "streams.json"))
        routes = load_routes(str(case_dir / "routes.json"))
        max_priority_level = assign_priority_classes(streams)
        cbs = CBSConfig.from_legacy_inputs(max_priority_level=max_priority_level)

        results = analyze(streams, routes, links, cbs, fixed_point=False)

        self.assertAlmostEqual(results[0], 603.2, places=6)
        self.assertAlmostEqual(results[1], 603.2, places=6)
        self.assertAlmostEqual(results[4], 884.48, places=6)
        self.assertAlmostEqual(results[6], 808.0, places=6)

    def test_three_cbs_class_case_produces_valid_wcds(self) -> None:
        case_dir = PROJECT_ROOT / "Required Files" / "test_case_2"
        _, links = load_topology(str(case_dir / "topology.json"))
        streams = load_streams(str(case_dir / "streams.json"))
        routes = load_routes(str(case_dir / "routes.json"))
        max_priority_level = assign_priority_classes(streams)
        cbs = CBSConfig.from_legacy_inputs(max_priority_level=max_priority_level)

        results = analyze(streams, routes, links, cbs, fixed_point=False)

        self.assertGreaterEqual(max_priority_level, 2)
        for stream in streams:
            self.assertIsNotNone(results[stream.id])
            self.assertGreater(results[stream.id], 0.0)

    def test_fixed_point_is_no_worse_than_single_instance(self) -> None:
        case_dir = PROJECT_ROOT / "Required Files" / "test_case_1"
        _, links = load_topology(str(case_dir / "topology.json"))
        streams = load_streams(str(case_dir / "streams.json"))
        routes = load_routes(str(case_dir / "routes.json"))
        max_priority_level = assign_priority_classes(streams)
        cbs = CBSConfig.from_legacy_inputs(max_priority_level=max_priority_level)

        single_results = analyze(streams, routes, links, cbs, fixed_point=False)
        fixed_point_results = analyze(streams, routes, links, cbs, fixed_point=True)

        for stream in streams:
            if stream.is_best_effort:
                continue
            self.assertIsNotNone(single_results[stream.id])
            self.assertIsNotNone(fixed_point_results[stream.id])
            self.assertLessEqual(fixed_point_results[stream.id], single_results[stream.id] + 1e-9)


if __name__ == "__main__":
    unittest.main()
