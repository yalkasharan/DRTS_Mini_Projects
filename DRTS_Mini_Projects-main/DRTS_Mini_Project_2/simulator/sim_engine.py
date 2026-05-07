"""
Discrete-event simulator for TSN AVB networks with an arbitrary number of
priority queues.
"""
import heapq
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

_ARR = 0
_DONE = 1
_WAKE = 2


@dataclass
class SimFrame:
    stream_id: int
    frame_instance: int
    size_bytes: int
    priority_level: int
    path_links: list
    current_hop: int
    source_time: float

    def tx_time(self, bandwidth_mbps: float) -> float:
        return (self.size_bytes * 8) / bandwidth_mbps


class OutputPort:
    _EPSILON = 1e-9

    def __init__(self, link_id: str, bandwidth_mbps: float, max_priority_level: int, cbs_config) -> None:
        self.link_id = link_id
        self.bw = bandwidth_mbps
        self.max_priority_level = max_priority_level
        self.cbs = cbs_config

        self.queues: Dict[int, deque] = {level: deque() for level in range(max_priority_level + 1)}
        self.credits: Dict[int, float] = {level: 0.0 for level in range(1, max_priority_level + 1)}
        self._t = 0.0

        self.tx_frame: Optional[SimFrame] = None
        self.tx_class: Optional[int] = None

    def update(self, now: float) -> None:
        dt = now - self._t
        if dt <= 0.0:
            return
        self._t = now

        for level in range(1, self.max_priority_level + 1):
            if self.tx_class == level:
                self.credits[level] -= dt * self.cbs.send_slope(level)
            elif self.queues[level]:
                self.credits[level] += dt * self.cbs.idle_slope(level)
            if not self.queues[level] and self.credits[level] > 0.0:
                self.credits[level] = 0.0

    def select(self) -> Tuple[Optional[SimFrame], Optional[int]]:
        for level in range(self.max_priority_level, 0, -1):
            if self.queues[level] and self.credits[level] >= -self._EPSILON:
                return self.queues[level][0], level
        if self.queues[0]:
            return self.queues[0][0], 0
        return None, None

    def credit_ready_time(self, now: float) -> Optional[float]:
        if self.queues[0]:
            return None
        candidates = []
        for level in range(1, self.max_priority_level + 1):
            if self.queues[level] and self.credits[level] < 0.0:
                candidates.append(now + (-self.credits[level]) / self.cbs.idle_slope(level))
        return min(candidates) if candidates else None

    def enqueue(self, frame: SimFrame) -> None:
        self.queues[frame.priority_level].append(frame)

    def dequeue(self, priority_level: int) -> SimFrame:
        return self.queues[priority_level].popleft()

    @property
    def idle(self) -> bool:
        return self.tx_frame is None


class Simulator:
    def __init__(self, streams, routes, links, cbs_config, duration_us: float, warmup_us: float = 0.0, log_credits: bool = False) -> None:
        self.streams = streams
        self.duration_us = duration_us
        self.warmup_us = warmup_us
        self.log_credits = log_credits
        self.credit_log: list = []

        self._link_map = {(link.source, link.source_port): link for link in links}
        self._route_map = {route.flow_id: route for route in routes}
        self.max_priority_level = max((stream.priority_level for stream in streams), default=0)

        self.ports: Dict[str, OutputPort] = {
            link.id: OutputPort(link.id, link.bandwidth_mbps, self.max_priority_level, cbs_config)
            for link in links
        }

        self._paths: Dict[int, list] = {}
        for stream in streams:
            route = self._route_map.get(stream.id)
            if route:
                self._paths[stream.id] = self._resolve(route.paths[0])

        self.response_times: Dict[int, List[float]] = {stream.id: [] for stream in streams}
        self._heap: list = []
        self._seq = 0

    def _resolve(self, path: list) -> list:
        result = []
        for hop in path[:-1]:
            key = (hop["node"], hop["port"])
            link = self._link_map.get(key)
            if link is None:
                raise ValueError(
                    f"No link found: node '{hop['node']}' egress port {hop['port']}. "
                    "Ensure topology.json and routes.json are consistent."
                )
            result.append(link)
        return result

    def _snapshot_port_credits(self, time: float, port: 'OutputPort', event_type: str = "") -> None:
        if not self.log_credits:
            return
        for level in range(1, port.max_priority_level + 1):
            if self.max_priority_level == 2:
                label = "CLASS_A" if level == 2 else "CLASS_B"
            else:
                label = f"CBS_{level}"
            self.credit_log.append({
                "time_us": time,
                "link_id": port.link_id,
                "queue_class": label,
                "credit": port.credits[level],
                "event_type": event_type,
            })

    def _push(self, time: float, kind: int, data) -> None:
        heapq.heappush(self._heap, (time, self._seq, kind, data))
        self._seq += 1

    def _try_start(self, port: OutputPort, now: float) -> None:
        frame, priority_level = port.select()
        if frame is None:
            wake = port.credit_ready_time(now)
            if wake is not None:
                self._push(wake, _WAKE, port.link_id)
            return

        port.dequeue(priority_level)
        port.tx_frame = frame
        port.tx_class = priority_level
        self._push(now + frame.tx_time(port.bw), _DONE, port.link_id)

    def _init_arrivals(self) -> None:
        for stream in self.streams:
            path = self._paths.get(stream.id)
            if not path:
                continue
            release = 0.0
            instance = 0
            while release < self.duration_us:
                frame = SimFrame(
                    stream_id=stream.id,
                    frame_instance=instance,
                    size_bytes=stream.size_bytes,
                    priority_level=stream.priority_level,
                    path_links=path,
                    current_hop=0,
                    source_time=release,
                )
                self._push(release, _ARR, (frame, path[0].id))
                release += stream.period_us
                instance += 1

    def run(self) -> Dict[int, List[float]]:
        self._init_arrivals()

        while self._heap:
            time, _seq, kind, data = heapq.heappop(self._heap)
            if time > self.duration_us:
                break

            if kind == _ARR:
                frame, link_id = data
                port = self.ports[link_id]
                port.update(time)
                self._snapshot_port_credits(time, port, "arr")
                port.enqueue(frame)
                if port.idle:
                    self._try_start(port, time)

            elif kind == _DONE:
                port = self.ports[data]
                port.update(time)
                self._snapshot_port_credits(time, port, "tx_end")
                frame = port.tx_frame
                port.tx_frame = None
                port.tx_class = None

                current_link = frame.path_links[frame.current_hop]
                next_hop = frame.current_hop + 1

                if next_hop < len(frame.path_links):
                    frame.current_hop = next_hop
                    next_link = frame.path_links[next_hop]
                    self._push(time + current_link.delay_us, _ARR, (frame, next_link.id))
                elif frame.source_time >= self.warmup_us:
                    self.response_times[frame.stream_id].append(time - frame.source_time)

                self._try_start(port, time)

            elif kind == _WAKE:
                port = self.ports[data]
                if port.idle:
                    port.update(time)
                    self._snapshot_port_credits(time, port, "wake")
                    self._try_start(port, time)

        return self.response_times
