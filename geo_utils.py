"""
geo_utils.py
Core geospatial + payout logic for the Find & Reward geo-bounty prototype.
Kept dependency-free (stdlib only) so it can be unit tested or reused
outside of Streamlit (e.g. in a FastAPI backend later).
"""

import math
import random

EARTH_RADIUS_KM = 6371.0


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Great-circle distance in kilometers between two (lat, lon) points,
    using the Haversine formula.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def find_users_in_radius(bounty_lat: float, bounty_lon: float, radius_km: float, users: list) -> list:
    """
    Filter a list of user dicts (each with 'lat', 'lon') down to the ones
    inside the paid broadcast radius, sorted nearest-first.

    Returns copies of the user dicts augmented with 'distance_km'.
    """
    nearby = []
    for u in users:
        d = haversine_distance(bounty_lat, bounty_lon, u["lat"], u["lon"])
        if d <= radius_km:
            enriched = dict(u)
            enriched["distance_km"] = round(d, 3)
            nearby.append(enriched)
    nearby.sort(key=lambda x: x["distance_km"])
    return nearby


def split_reward(total_reward: float, finder_pct: int = 50) -> tuple:
    """
    Split the total bounty into (finder_share, platform_share) once a claim
    is verified and escrow is released. finder_pct is the percentage of the
    total that goes to the finder; the remainder is the platform fee.
    """
    finder_pct = max(0, min(100, finder_pct))
    finder_share = round(total_reward * finder_pct / 100.0, 2)
    platform_share = round(total_reward - finder_share, 2)
    return finder_share, platform_share


def random_point_within_radius(center_lat: float, center_lon: float, max_radius_km: float, rng=None):
    """
    Generate a uniformly-distributed random point within max_radius_km of a
    center point. Used only to seed realistic-looking demo users for the
    prototype -- a production system would use real device GPS.
    """
    rng = rng or random
    r = max_radius_km * math.sqrt(rng.random())
    theta = rng.random() * 2 * math.pi

    d_lat = (r / EARTH_RADIUS_KM) * (180.0 / math.pi)
    d_lon = (r / EARTH_RADIUS_KM) * (180.0 / math.pi) / math.cos(math.radians(center_lat))

    new_lat = center_lat + d_lat * math.cos(theta)
    new_lon = center_lon + d_lon * math.sin(theta)
    return round(new_lat, 6), round(new_lon, 6)


if __name__ == "__main__":
    # Quick sanity checks -- run with `python3 geo_utils.py`
    mumbai = (19.0760, 72.8777)
    bandra = (19.0596, 72.8295)
    d = haversine_distance(*mumbai, *bandra)
    print(f"Mumbai -> Bandra: {d:.2f} km (expected ~5-6 km)")

    demo_users = [
        {"id": 1, "name": "Aisha", "lat": 19.0700, "lon": 72.8800},
        {"id": 2, "name": "Rohan", "lat": 19.2000, "lon": 72.9700},  # far away
        {"id": 3, "name": "Priya", "lat": 19.0800, "lon": 72.8750},
    ]
    nearby = find_users_in_radius(19.0760, 72.8777, 2.0, demo_users)
    print("Nearby users within 2km:", [u["name"] for u in nearby])

    finder, platform = split_reward(500, 50)
    print(f"Reward split on ₹500: finder=₹{finder}, platform=₹{platform}")
