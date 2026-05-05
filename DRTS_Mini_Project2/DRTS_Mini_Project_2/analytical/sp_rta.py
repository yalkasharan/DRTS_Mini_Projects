import math
from typing import Dict, List, Optional, Tuple

from model import Link, Route, Stream
from wcrt_analysis import get_path_links


def _tx_time(size_bytes: int, bandwidth_mbps: float) -> float:
    return (size_bytes * 8) / bandwidth_mbps


def _build_link_lookup(links: List[Link]) -> Dict[Tuple[str, int], Link]:
    return {(link.source, link.source_port): link for link in links}


def _streams_on_link(
    link: Link,
    streams: List[Stream],
    route_map: Dict[int, Route],
    link_lookup: Dict[Tuple[str, int], Link],
) -> List[Stream]:
    result = []
    for stream in streams:
        route = route_map.get(stream.id)
        if route is None:
            continue
        for path in route.paths:
            if any(path_link.id == link.id for path_link in get_path_links(path, link_lookup)):
                result.append(stream)
                break
    return result


def _rta_link(stream: Stream, link: Link, coflows: List[Stream]) -> Optional[float]:
    bandwidth = link.bandwidth_mbps
    own_tx = _tx_time(stream.size_bytes, bandwidth)
    higher_priority = [other for other in coflows if other.priority_level > stream.priority_level]

    response = own_tx
    for _ in range(1000):
        interference = sum(
            math.ceil(response / other.period_us) * _tx_time(other.size_bytes, bandwidth)
            for other in higher_priority
        )
        updated = own_tx + interference
        if abs(updated - response) <= 1e-9:
            return updated
        response = updated
    return None


def compute_sp_wcd(
    stream: Stream,
    route_map: Dict[int, Route],
    link_lookup: Dict[Tuple[str, int], Link],
    all_streams: List[Stream],
) -> Optional[float]:
    route = route_map.get(stream.id)
    if route is None:
        return None

    total = 0.0
    for link in get_path_links(route.paths[0], link_lookup):
        coflows = _streams_on_link(link, all_streams, route_map, link_lookup)
        link_wcrt = _rta_link(stream, link, coflows)
        if link_wcrt is None:
            return None
        total += link_wcrt + link.delay_us
    return total


def analyze_sp(streams: List[Stream], routes: List[Route], links: List[Link]) -> Dict[int, Optional[float]]:
    route_map = {route.flow_id: route for route in routes}
    link_lookup = _build_link_lookup(links)
    return {
        stream.id: compute_sp_wcd(stream, route_map, link_lookup, streams)
        for stream in streams
    }
