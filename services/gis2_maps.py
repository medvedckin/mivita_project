import json
import logging
import re
import time

import httpx

from config import settings

logger = logging.getLogger(__name__)

GEOCODE_URL = "https://catalog.api.2gis.com/3.0/items"
TSP_CREATE_URL = "https://routing.api.2gis.com/logistics/vrp/1.1.0/create"
TSP_STATUS_URL = "https://routing.api.2gis.com/logistics/vrp/1.1.0/status"
ROUTING_URL = "https://routing.api.2gis.com/routing/7.0.0/global"

TSP_POLL_INTERVAL = 2
TSP_MAX_POLLS = 15


def geocode_address(address: str) -> tuple[float, float] | None:
    """Convert an address to (longitude, latitude) via 2GIS Catalog API."""
    if not settings.gis2_maps_api_key:
        logger.warning("GIS2_MAPS_API_KEY not set — skipping geocoding")
        return None

    try:
        resp = httpx.get(
            GEOCODE_URL,
            params={
                "q": address,
                "key": settings.gis2_maps_api_key,
                "fields": "items.point",
                "type": "building",
            },
            timeout=10,
        )

        if resp.status_code == 403:
            logger.warning(
                "Geocoding auth failed for '%s' — check GIS2_MAPS_API_KEY", address
            )
            return None

        resp.raise_for_status()
        data = resp.json()
        items = data.get("result", {}).get("items", [])
        if not items:
            logger.warning("No geocode results for address: %s", address)
            return None

        point = items[0].get("point")
        if not point:
            return None

        lat = point.get("lat")
        lon = point.get("lon")
        if lat is None or lon is None:
            return None

        return (float(lon), float(lat))
    except Exception as exc:
        logger.error("Geocoding failed for '%s': %s", address, exc)
        return None


def optimize_route(
    waypoints: list[dict],
) -> dict:
    """Optimise waypoint ordering via 2GIS TSP API.

    Each waypoint: { "address": str, "lat": float, "lon": float }
    Returns: { "order": list[int] (indices into original list),
               "total_distance_m": float,
               "total_duration_min": float,
               "polyline": str | None }
    """
    result: dict = {
        "order": list(range(len(waypoints))),
        "total_distance_m": 0,
        "total_duration_min": 0,
        "polyline": None,
    }

    if len(waypoints) < 2:
        return result

    coords = [(w["lon"], w["lat"]) for w in waypoints]
    has_coords = all(c[0] is not None and c[1] is not None for c in coords)

    if not has_coords or not settings.gis2_maps_api_key:
        return _fallback_sort(waypoints, coords)

    result = _optimize_via_tsp(waypoints, coords)
    return result


def _optimize_via_tsp(
    waypoints: list[dict], coords: list[tuple[float | None, float | None]]
) -> dict:
    """Use 2GIS TSP API async + optionally Routing API for geometry."""
    try:
        task_body = {
            "agents": [
                {
                    "agent_id": 0,
                    "start_waypoint_id": 0,
                }
            ],
            "waypoints": [
                {
                    "waypoint_id": i,
                    "point": {"lat": lat, "lon": lon},
                }
                for i, (lon, lat) in enumerate(coords)
            ],
            "start_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        create_resp = httpx.post(
            TSP_CREATE_URL,
            params={"key": settings.gis2_maps_api_key},
            json=task_body,
            timeout=30,
        )

        if create_resp.status_code != 201:
            logger.warning("TSP create failed: %s", create_resp.text)
            return _fallback_sort(waypoints, coords)

        task_data = create_resp.json()
        task_id = task_data.get("task_id")
        if not task_id:
            return _fallback_sort(waypoints, coords)

        solution = _poll_tsp_result(task_id)
        if not solution:
            return _fallback_sort(waypoints, coords)

        routes = solution.get("routes", [])
        if not routes:
            return _fallback_sort(waypoints, coords)

        route0 = routes[0]
        ordered_ids = route0.get("points", [])
        total_distance_m = route0.get("distance", 0) or 0
        total_duration_sec = route0.get("duration", 0) or 0

        ordered_indices = _map_tsp_order(ordered_ids, len(waypoints), coords)

        polyline = None
        if len(ordered_indices) >= 2:
            polyline = _build_route_wkt(
                [coords[i] for i in ordered_indices]
            )

        return {
            "order": ordered_indices,
            "total_distance_m": float(total_distance_m),
            "total_duration_min": round(total_duration_sec / 60, 1),
            "polyline": polyline,
        }

    except Exception as exc:
        logger.error("TSP optimisation failed: %s", exc)
        return _fallback_sort(waypoints, coords)


def _poll_tsp_result(task_id: str) -> dict | None:
    """Poll TSP task status until Done / Fail / timeout."""
    for _ in range(TSP_MAX_POLLS):
        time.sleep(TSP_POLL_INTERVAL)
        try:
            status_resp = httpx.get(
                TSP_STATUS_URL,
                params={"task_id": task_id, "key": settings.gis2_maps_api_key},
                timeout=15,
            )
            if status_resp.status_code != 200:
                continue

            status_data = status_resp.json()
            st = status_data.get("status")

            if st == "Done":
                sol_url = (
                    status_data.get("urls", {}) or {}
                ).get("url_vrp_solution")
                if sol_url:
                    sol_resp = httpx.get(sol_url, timeout=30)
                    if sol_resp.status_code == 200:
                        return sol_resp.json()
                return None

            if st in ("Fail", "Partial"):
                logger.warning(
                    "TSP task %s status=%s", task_id, st
                )
                return None

        except Exception as exc:
            logger.error("TSP poll error for %s: %s", task_id, exc)

    logger.warning("TSP task %s timed out", task_id)
    return None


def _map_tsp_order(
    ordered_ids: list[int], total_count: int, coords: list
) -> list[int]:
    """Map TSP waypoint_ids back to original indices.

    TSP returns the first point (id=0) as the route start and the rest
    in optimal order.  We keep the relative order of all waypoints_id
    that appear, and append any missing ones at the end.
    """
    seen = set(ordered_ids)
    ordered = list(ordered_ids)
    for i in range(total_count):
        if i not in seen:
            ordered.append(i)
    # Clip to valid indices
    return [i for i in ordered if 0 <= i < total_count]


def _build_route_wkt(
    ordered_coords: list[tuple[float, float]],
) -> str | None:
    """Build a detailed route via 2GIS Routing API and extract WKT polyline."""
    try:
        points = [
            {"lat": lat, "lon": lon} for lon, lat in ordered_coords
        ]

        routing_resp = httpx.post(
            ROUTING_URL,
            params={"key": settings.gis2_maps_api_key},
            json={
                "points": points,
                "route_mode": "fastest",
                "transport": "car",
            },
            timeout=30,
        )

        if routing_resp.status_code != 200:
            return None

        routing_data = routing_resp.json()
        route_results = routing_data.get("result", [])
        if not route_results:
            return None

        all_coords = _extract_wkt_coords(route_results[0])
        if all_coords:
            return json.dumps(all_coords)

        return None

    except Exception as exc:
        logger.error("Route building failed: %s", exc)
        return None


def _extract_wkt_coords(route_result: dict) -> list[list[float]]:
    """Extract coordinate pairs from WKT LINESTRINGs in route result."""
    all_coords: list[list[float]] = []
    seen_points: set[tuple[float, float]] = set()

    maneuvers = route_result.get("maneuvers", [])
    for maneuver in maneuvers:
        path = maneuver.get("outcoming_path", {}) or {}
        geometries = path.get("geometry", []) or []
        for geom in geometries:
            selection = geom.get("selection", "")
            if not selection:
                continue
            match = re.search(r"LINESTRING\(([^)]+)\)", selection)
            if not match:
                continue
            point_strs = match.group(1).split(",")
            for ps in point_strs:
                ps = ps.strip()
                if " " not in ps:
                    continue
                parts = ps.split()
                if len(parts) != 2:
                    continue
                try:
                    lon, lat = float(parts[0]), float(parts[1])
                    key = (round(lon, 6), round(lat, 6))
                    if key not in seen_points:
                        seen_points.add(key)
                        all_coords.append([lon, lat])
                except (ValueError, TypeError):
                    continue

    return all_coords


def _fallback_sort(
    waypoints: list[dict], coords: list[tuple[float | None, float | None]]
) -> dict:
    """Simple fallback: sort by longitude then latitude (west→east, south→north)."""
    indexed = list(enumerate(coords))
    valid = [(i, (c[0] or 0, c[1] or 0)) for i, c in indexed]
    valid.sort(key=lambda x: (x[1][0] or 0, x[1][1] or 0))
    order = [i for i, _ in valid]
    return {
        "order": order,
        "total_distance_m": 0,
        "total_duration_min": 0,
        "polyline": None,
    }
