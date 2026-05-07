"""
Parse TSN network JSON configuration files into model objects.
"""
import json
from typing import List, Tuple

from model import Link, Route, Stream, priority_label

_TO_US: dict = {
    "NANO_SECOND": 1e-3,
    "MICRO_SECOND": 1.0,
    "MILLI_SECOND": 1e3,
    "SECOND": 1e6,
}


def load_topology(filepath: str) -> Tuple[float, List[Link]]:
    with open(filepath, encoding="utf-8") as handle:
        topo = json.load(handle)["topology"]

    delay_units = topo.get("delay_units", "MICRO_SECOND")
    us_factor = _TO_US.get(delay_units, 1.0)
    default_bw = float(topo.get("default_bandwidth_mbps", 1000.0))

    links = []
    for lk in topo["links"]:
        links.append(
            Link(
                id=lk["id"],
                source=lk["source"],
                source_port=int(lk["sourcePort"]),
                destination=lk["destination"],
                destination_port=int(lk["destinationPort"]),
                bandwidth_mbps=float(lk.get("bandwidth_mbps", default_bw)),
                delay_us=float(lk.get("delay", 0.0)) * us_factor,
            )
        )
    return default_bw, links


def load_streams(filepath: str) -> List[Stream]:
    with open(filepath, encoding="utf-8") as handle:
        data = json.load(handle)

    delay_units = data.get("delay_units", "MICRO_SECOND")
    us_factor = _TO_US.get(delay_units, 1.0)

    streams = []
    for item in data["streams"]:
        destinations = [
            {"id": dest["id"], "deadline": float(dest["deadline"]) * us_factor}
            for dest in item["destinations"]
        ]
        streams.append(
            Stream(
                id=int(item["id"]),
                name=item.get("name", f"Stream{item['id']}"),
                source=item["source"],
                destinations=destinations,
                pcp=int(item["PCP"]),
                size_bytes=int(item["size"]),
                period_us=float(item["period"]) * us_factor,
            )
        )
    return streams


def load_routes(filepath: str) -> List[Route]:
    with open(filepath, encoding="utf-8") as handle:
        data = json.load(handle)

    return [Route(flow_id=int(route["flow_id"]), paths=route["paths"]) for route in data["routes"]]


def assign_priority_classes(streams: List[Stream]) -> int:
    """
    Map distinct PCP values onto contiguous numeric priority levels.

    The lowest distinct PCP becomes priority 0 (Best Effort), and each higher
    distinct PCP becomes the next CBS queue. This generalizes the original
    PCP 2 -> Class A, PCP 1 -> Class B, PCP 0 -> Best Effort setup.
    """
    if not streams:
        return 0

    distinct_pcps = sorted({stream.pcp for stream in streams})
    pcp_to_level = {pcp: level for level, pcp in enumerate(distinct_pcps)}
    max_priority_level = len(distinct_pcps) - 1

    for stream in streams:
        stream.priority_level = pcp_to_level[stream.pcp]
        stream.max_priority_level = max_priority_level
        stream.priority_class = priority_label(stream.priority_level, max_priority_level)

    return max_priority_level
