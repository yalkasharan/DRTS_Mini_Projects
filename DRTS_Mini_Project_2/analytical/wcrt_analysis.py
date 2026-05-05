"""
Worst-Case Response Time (WCRT) analysis for Ethernet AVB with CBS.

This module keeps the original single-instance project model as the default and
adds:
  - an arbitrary number of CBS queues above Best Effort
  - an optional fixed-point mode

Formula notes
-------------
The same-priority and recursive higher-priority structure follows the
independent per-class reasoning of Cao et al. 2016/2018. In particular, the
recursive higher-priority accumulation in `_single_instance_cbs_link_wcrt`
generalizes the original Class B expression to priority level k by folding the
higher CBS queues one by one from lower to higher priority, as discussed by
Cao et al. 2018 for arbitrary AVB priority classes.

Credit Recovery Ratio
---------------------
The credit recovery factor used in SPI and HPI calculations is computed as:
  ratio = send_slope / idle_slope
  
This represents how quickly credits are consumed (send_slope) relative to how 
quickly they recover (idle_slope). A higher ratio indicates faster credit 
depletion and slower recovery, allowing more same-priority and higher-priority 
interference. This follows Cao et al. 2016 formula for CBS-shaped interference.
"""
import math
from typing import Dict, List, Optional, Tuple

from model import BEST_EFFORT, CBSConfig, Link, Route, Stream


def _tx_time(size_bytes: int, bandwidth_mbps: float) -> float:
    return (size_bytes * 8) / bandwidth_mbps


def _build_link_lookup(links: List[Link]) -> Dict[Tuple[str, int], Link]:
    return {(link.source, link.source_port): link for link in links}


def get_path_links(path: List[dict], link_lookup: Dict[Tuple[str, int], Link]) -> List[Link]:
    """
    Return the output links along the path that contribute to the analysis.

    Routes encode every visited node from source to destination.
    Each node (except the final destination) has an output link that must be
    analyzed for CBS scheduling delay. This includes the source end-system
    and all intermediate switches.
    
    Example: For path [ES1, SW1, ES0], we analyze:
      - Link from ES1 (port 0) to SW1
      - Link from SW1 (port 6) to ES0
    """
    # All nodes except the destination node have output links to analyze
    transmitting_hops = path[:-1]
    traversed = []
    for hop in transmitting_hops:
        key = (hop["node"], hop["port"])
        link = link_lookup.get(key)
        if link is None:
            raise ValueError(
                f"No link found leaving node '{hop['node']}' on port {hop['port']}. "
                "Check that topology.json and routes.json are consistent."
            )
        traversed.append(link)
    return traversed


def get_coflows(
    link: Link,
    all_streams: List[Stream],
    route_map: Dict[int, Route],
    link_lookup: Dict[Tuple[str, int], Link],
) -> List[Stream]:
    result = []
    for stream in all_streams:
        route = route_map.get(stream.id)
        if route is None:
            continue
        for path in route.paths:
            path_links = get_path_links(path, link_lookup)
            if any(candidate.id == link.id for candidate in path_links):
                result.append(stream)
                break
    return result


def _max_tx_time(streams: List[Stream], bandwidth_mbps: float) -> float:
    return max((_tx_time(stream.size_bytes, bandwidth_mbps) for stream in streams), default=0.0)


def _same_priority_interference(
    stream: Stream,
    coflows: List[Stream],
    bandwidth_mbps: float,
    cbs: CBSConfig,
    jobs_in_window: int = 1,
) -> float:
    """
    Compute same-priority interference with CBS credit recovery factor.
    
    Formula (Cao et al. 2016):
      SPI = sum of (1 + send_slope / idle_slope) * C_j   for j at same priority
      
    The ratio send_slope / idle_slope quantifies credit depletion vs. recovery:
    - send_slope: rate at which credits decrease during transmission (positive value)
    - idle_slope: rate at which credits increase when queue is backlogged (positive value)
    - Higher ratio → faster credit consumption, slower recovery → more interference
    """
    ratio = cbs.send_slope(stream.priority_level) / cbs.idle_slope(stream.priority_level)
    return sum(
        jobs_in_window * _tx_time(other.size_bytes, bandwidth_mbps) * (1.0 + ratio)
        for other in coflows
        if other.priority_level == stream.priority_level and other.id != stream.id
    )


def _recursive_higher_priority_term(
    priority_level: int,
    coflows: List[Stream],
    bandwidth_mbps: float,
    cbs: CBSConfig,
) -> float:
    """
    Generalized recursive higher-priority accumulation.

    For k = 1 in the classic A/B/BE case, this reduces to the original
    Cao 2016 Class B term:
      Cmax_BE * (1 + alpha_A^+ / alpha_A^-) + Cmax_A
    """
    lower_blocking = _max_tx_time(
        [stream for stream in coflows if stream.priority_level < priority_level],
        bandwidth_mbps,
    )
    accumulated = lower_blocking
    for higher_level in range(priority_level + 1, max((s.priority_level for s in coflows), default=0) + 1):
        if higher_level <= 0:
            continue
        higher_streams = [stream for stream in coflows if stream.priority_level == higher_level]
        if not higher_streams:
            continue
        accumulated = (
            accumulated * (1.0 + cbs.send_slope(higher_level) / cbs.idle_slope(higher_level))
            + _max_tx_time(higher_streams, bandwidth_mbps)
        )
    return accumulated


def _single_instance_cbs_link_wcrt(
    stream: Stream,
    link: Link,
    coflows: List[Stream],
    cbs: CBSConfig,
) -> float:
    """
    Single-instance CBS bound.

    The same-priority term follows Cao et al. 2016. The recursive higher-class
    accumulation generalizes the two-CBS-queue case to arbitrary priority
    levels following the per-class decomposition of Cao et al. 2018.
    """
    bandwidth = link.bandwidth_mbps
    own_tx = _tx_time(stream.size_bytes, bandwidth)
    same_priority = _same_priority_interference(stream, coflows, bandwidth, cbs)

    if stream.priority_level == stream.max_priority_level:
        # Highest priority keeps the legacy non-preemptive blocking behavior, so
        # test-case-1 remains identical.
        lower_blocking = _max_tx_time(
            [candidate for candidate in coflows if candidate.priority_level < stream.priority_level],
            bandwidth,
        )
        return own_tx + same_priority + lower_blocking

    return own_tx + same_priority + _recursive_higher_priority_term(
        stream.priority_level,
        coflows,
        bandwidth,
        cbs,
    )


def _fixed_point_cbs_link_wcrt(
    stream: Stream,
    link: Link,
    coflows: List[Stream],
    cbs: CBSConfig,
) -> Optional[float]:
    """
    Fixed-point CBS busy-period analysis.

    Uses the CBS-bounded formula for both same-priority and higher-priority
    interference, following the per-class credit recovery reasoning of
    Cao et al. 2016/2018:

      R_{n+1} = C_i + B_lower + SPI(R_n) + HPI(R_n)

    where:
      SPI(R) = sum ceil(R / T_j) * C_j * (1 + alpha^+ / alpha^-)   [same class]
      HPI(R) uses CBS-bounded credit recovery per higher-priority class,
              rather than the SP-style raw busy-period accumulation.

    For the highest CBS class, HPI reduces to non-preemptive lower blocking.
    For lower CBS classes (e.g. Class B), the HPI incorporates the credit
    recovery factor of each higher CBS class bounding how much each class
    can interfere within the response window.
    """
    bandwidth = link.bandwidth_mbps
    own_tx = _tx_time(stream.size_bytes, bandwidth)
    deadline = stream.destinations[0]["deadline"] if stream.destinations else math.inf

    # Non-preemptive blocking from lower-priority traffic (at most one frame)
    lower_blocking = _max_tx_time(
        [candidate for candidate in coflows if candidate.priority_level < stream.priority_level],
        bandwidth,
    )

    # Same-priority streams
    same_priority = [
        other
        for other in coflows
        if other.priority_level == stream.priority_level and other.id != stream.id
    ]

    # Higher-priority streams grouped by CBS class
    higher_classes: Dict[int, List[Stream]] = {}
    max_level = max((s.priority_level for s in coflows), default=0)
    for level in range(stream.priority_level + 1, max_level + 1):
        streams_at_level = [s for s in coflows if s.priority_level == level]
        if streams_at_level:
            higher_classes[level] = streams_at_level

    spi_ratio = cbs.send_slope(stream.priority_level) / cbs.idle_slope(stream.priority_level)

    response = own_tx
    for _ in range(1000):
        # Same-priority interference with CBS credit recovery
        same_interference = sum(
            math.ceil(response / other.period_us)
            * _tx_time(other.size_bytes, bandwidth)
            * (1.0 + spi_ratio)
            for other in same_priority
        )

        # Higher-priority interference: CBS-bounded per-class
        if stream.priority_level == stream.max_priority_level:
            # Highest CBS class: only non-preemptive lower blocking
            hpi = lower_blocking
        else:
            # CBS-bounded HPI: for each higher CBS class, the interference
            # within window R is bounded by the number of arrivals scaled by
            # the credit recovery factor of that class.
            # This follows the recursive structure of Cao et al. 2018:
            #   accumulated = lower_blocking
            #   for each higher class h (ascending priority):
            #     accumulated = accumulated * (1 + alpha_h^+ / alpha_h^-)
            #                 + sum ceil(R / T_j) * C_j   for j in class h
            accumulated = lower_blocking
            for level in sorted(higher_classes.keys()):
                hpi_ratio = cbs.send_slope(level) / cbs.idle_slope(level)
                higher_demand = sum(
                    math.ceil(response / s.period_us)
                    * _tx_time(s.size_bytes, bandwidth)
                    for s in higher_classes[level]
                )
                accumulated = accumulated * (1.0 + hpi_ratio) + higher_demand
            hpi = accumulated

        updated = own_tx + hpi + same_interference
        if updated > deadline:
            return None
        if abs(updated - response) <= 1e-9:
            return updated
        response = updated
    return None


def _best_effort_link_wcrt(stream: Stream, link: Link, coflows: List[Stream]) -> float:
    bandwidth = link.bandwidth_mbps
    own_tx = _tx_time(stream.size_bytes, bandwidth)
    interference = sum(
        math.ceil(own_tx / other.period_us) * _tx_time(other.size_bytes, bandwidth)
        for other in coflows
        if other.priority_level > 0
    )
    return own_tx + interference


def compute_e2e_wcrt(
    stream: Stream,
    route_map: Dict[int, Route],
    link_lookup: Dict[Tuple[str, int], Link],
    all_streams: List[Stream],
    cbs: CBSConfig,
    include_propagation: bool = False,
    fixed_point: bool = False,
) -> Optional[float]:
    route = route_map.get(stream.id)
    if route is None:
        return None

    path_links = get_path_links(route.paths[0], link_lookup)
    total = 0.0

    for link in path_links:
        coflows = get_coflows(link, all_streams, route_map, link_lookup)
        if stream.is_best_effort:
            link_wcrt = _best_effort_link_wcrt(stream, link, coflows)
        elif fixed_point:
            link_wcrt = _fixed_point_cbs_link_wcrt(stream, link, coflows, cbs)
            if link_wcrt is None:
                return None
        else:
            link_wcrt = _single_instance_cbs_link_wcrt(stream, link, coflows, cbs)

        total += link_wcrt
        if include_propagation:
            total += link.delay_us

    return total


def analyze(
    streams: List[Stream],
    routes: List[Route],
    links: List[Link],
    cbs: CBSConfig,
    include_propagation: bool = False,
    fixed_point: bool = False,
) -> Dict[int, Optional[float]]:
    route_map = {route.flow_id: route for route in routes}
    link_lookup = _build_link_lookup(links)
    return {
        stream.id: compute_e2e_wcrt(
            stream,
            route_map,
            link_lookup,
            streams,
            cbs,
            include_propagation=include_propagation,
            fixed_point=fixed_point,
        )
        for stream in streams
    }
