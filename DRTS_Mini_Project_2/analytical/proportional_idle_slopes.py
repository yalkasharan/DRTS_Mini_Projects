"""
Proportional Idle Slope Computation

This module computes CBS idle slopes for each priority class based on per-link
stream utilization, removing the arbitrary 50/50 split and adapting to actual
traffic characteristics.

Algorithm:
----------
For each link L and priority class p:
  1. Compute utilization U_p(L) = sum of (frame_size / period) for streams in class p on link L
  2. Compute total utilization U_total(L) for all CBS classes on link L
  3. Allocate idle slope inversely proportional to utilization:
     idle_slope_p(L) = (1 - U_BE) * (1 - U_p / U_total)
  
  where U_BE is the Best Effort utilization (which does not participate in CBS scheduling).

This approach minimizes over-allocation to classes with heavy traffic while
reserving capacity for lighter classes, reducing pessimism in the bounds.
"""

from typing import Dict, List, Tuple
from model import Link, Stream


def compute_per_link_utilization(
    streams: List[Stream],
    links: List[Link],
) -> Dict[Tuple[str, int], Dict[int, float]]:
    """
    Compute per-link utilization for each priority class.
    
    Returns
    -------
    Dict mapping (link_id) -> {priority_level -> utilization}
        utilization = sum of (frame_size_bits / bandwidth_mbps / period_us) for streams at that priority
    """
    link_util = {}  # (link_id) -> {priority_level -> utilization}
    
    for link in links:
        link_util[link.id] = {}
    
    for stream in streams:
        # Find all links this stream traverses
        # For now, assume all streams traverse all links (simplified model)
        # In practice, use route information
        frame_bits = stream.size_bytes * 8
        period_us = stream.period_us
        
        for link in links:
            bandwidth_mbps = link.bandwidth_mbps
            utilization = (frame_bits / (bandwidth_mbps * 1e6)) / (period_us / 1e6)
            
            if stream.priority_level not in link_util[link.id]:
                link_util[link.id][stream.priority_level] = 0.0
            link_util[link.id][stream.priority_level] += utilization
    
    return link_util


def compute_proportional_idle_slopes(
    streams: List[Stream],
    links: List[Link],
    max_priority_level: int,
) -> Dict[int, float]:
    """
    Compute proportional idle slopes for each CBS priority class.
    
    Returns
    -------
    Dict[int, float]
        {priority_level -> idle_slope}
    """
    per_link_util = compute_per_link_utilization(streams, links)
    
    idle_slopes = {}
    idle_slopes[0] = 0.0  # Best Effort has no CBS shaping
    
    for level in range(1, max_priority_level + 1):
        # Collect utilizations across all links for this priority class
        all_util_at_level = []
        for link_id, class_utils in per_link_util.items():
            if level in class_utils:
                all_util_at_level.append(class_utils[level])
        
        if not all_util_at_level:
            # No streams at this priority level; use default
            idle_slopes[level] = 0.5
            continue
        
        # Use the maximum utilization across links (worst case)
        max_util = max(all_util_at_level)
        
        # Cap utilization at 0.95 to ensure positive send_slope
        max_util = min(max_util, 0.95)
        
        # Idle slope inversely proportional to utilization
        # Heavier traffic -> lower idle slope -> higher send slope -> more interference
        if max_util > 0:
            idle_slopes[level] = 1.0 - max_util
        else:
            idle_slopes[level] = 0.95  # Default for zero-utilization classes
    
    # Normalize if sum exceeds 1.0
    total = sum(idle_slopes.get(i, 0.0) for i in range(1, max_priority_level + 1))
    if total > 1.0:
        scale = 1.0 / total
        for level in range(1, max_priority_level + 1):
            idle_slopes[level] *= scale
    
    return idle_slopes


def compute_utilization_summary(
    streams: List[Stream],
    links: List[Link],
) -> Dict[int, float]:
    """
    Compute overall utilization per priority class.
    
    Returns
    -------
    Dict[int, float]
        {priority_level -> utilization}
    """
    utilization = {}
    
    for stream in streams:
        if stream.priority_level not in utilization:
            utilization[stream.priority_level] = 0.0
        
        frame_bits = stream.size_bytes * 8
        period_us = stream.period_us
        
        # Use the link with highest bandwidth for conservative estimate
        max_bandwidth = max((link.bandwidth_mbps for link in links), default=100.0)
        util = (frame_bits / (max_bandwidth * 1e6)) / (period_us / 1e6)
        utilization[stream.priority_level] += util
    
    return utilization
