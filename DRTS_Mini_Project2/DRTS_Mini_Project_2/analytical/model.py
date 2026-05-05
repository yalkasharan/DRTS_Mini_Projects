"""
Data model for TSN network WCRT analysis.

Priority model
--------------
Streams are mapped to numeric priority levels:
  0      -> Best Effort (non-CBS)
  1..N-1 -> CBS-shaped AVB queues, with N-1 being the highest priority.

For backwards compatibility with the original project write-up and outputs,
the classic three-level case still exposes the legacy labels:
  level 2 -> CLASS_A
  level 1 -> CLASS_B
  level 0 -> BEST_EFFORT
"""
from dataclasses import dataclass, field
from typing import Dict, List

BEST_EFFORT = "BEST_EFFORT"
CLASS_A = "CLASS_A"
CLASS_B = "CLASS_B"


def priority_label(priority_level: int, max_priority_level: int) -> str:
    """Return a human-readable label for a numeric priority level."""
    if priority_level == 0:
        return BEST_EFFORT
    if max_priority_level == 2:
        if priority_level == 2:
            return CLASS_A
        if priority_level == 1:
            return CLASS_B
    return f"CBS_{priority_level}"


def display_priority_label(priority_level: int, max_priority_level: int) -> str:
    """Return a CLI-friendly label."""
    label = priority_label(priority_level, max_priority_level)
    return {
        BEST_EFFORT: "Best Effort",
        CLASS_A: "Class A",
        CLASS_B: "Class B",
    }.get(label, f"CBS P{priority_level}")


@dataclass
class Link:
    """A directed (unidirectional) network link."""
    id: str
    source: str
    source_port: int
    destination: str
    destination_port: int
    bandwidth_mbps: float
    delay_us: float


@dataclass
class Stream:
    """A periodic real-time flow."""
    id: int
    name: str
    source: str
    destinations: List[Dict]
    pcp: int
    size_bytes: int
    period_us: float
    priority_level: int = 0
    max_priority_level: int = 0
    priority_class: str = BEST_EFFORT

    @property
    def is_best_effort(self) -> bool:
        return self.priority_level == 0


@dataclass
class Route:
    """Pre-computed path(s) for a single stream."""
    flow_id: int
    paths: List[List[Dict]]


@dataclass
class CBSConfig:
    """
    Credit-Based Shaper parameters, expressed as fractions of link bandwidth.

    All CBS queues default to 0.5 idle slope unless the CLI overrides are
    mapped onto the classic two-CBS-queue configuration.
    """
    idle_slopes: Dict[int, float] = field(default_factory=dict)
    default_idle_slope: float = 0.5

    @classmethod
    def from_legacy_inputs(
        cls,
        max_priority_level: int,
        idle_slope_a: float = 0.5,
        idle_slope_b: float = 0.5,
        default_idle_slope: float = 0.5,
    ) -> "CBSConfig":
        idle_slopes: Dict[int, float] = {}
        if max_priority_level >= 1:
            for level in range(1, max_priority_level + 1):
                idle_slopes[level] = default_idle_slope
            idle_slopes[max_priority_level] = idle_slope_a
            if max_priority_level >= 2:
                idle_slopes[max_priority_level - 1] = idle_slope_b
        return cls(idle_slopes=idle_slopes, default_idle_slope=default_idle_slope)

    def idle_slope(self, priority_level: int) -> float:
        if priority_level <= 0:
            return 0.0
        return self.idle_slopes.get(priority_level, self.default_idle_slope)

    def send_slope(self, priority_level: int) -> float:
        if priority_level <= 0:
            return 0.0
        return 1.0 - self.idle_slope(priority_level)

    @property
    def idle_slope_class_a(self) -> float:
        return self.idle_slope(2)

    @property
    def idle_slope_class_b(self) -> float:
        return self.idle_slope(1)

    @property
    def send_slope_class_a(self) -> float:
        return self.send_slope(2)

    @property
    def send_slope_class_b(self) -> float:
        return self.send_slope(1)
