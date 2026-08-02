# Find & Reward -- C++ CLI Simulation

An object-oriented, terminal-based simulation of the same geo-bounty platform as the
Streamlit prototype: post a bounty, broadcast it to nearby simulated users using real
Haversine distance, accept claims, and release a split reward through an in-memory
escrow ledger. No external dependencies -- standard library only.

## Build & run

```bash
g++ -std=c++17 -O2 -o geobounty main.cpp
./geobounty
```

On startup it seeds 16 demo users at reproducible random points around Mumbai
(19.0760, 72.8777) using a fixed RNG seed, so every run starts from the same state.

## Menu

```
1) Post a bounty                    -- fund escrow for a lost item/pet
2) List active bounties
3) Simulate broadcast               -- who falls inside the paid radius
4) Submit a 'found it' claim
5) Resolve pending claims           -- approve (splits + releases escrow) or reject
6) View escrow ledger
7) List demo users
0) Exit
```

When posting a bounty you specify the last-known location as a distance + bearing
from the city center (km, degrees) rather than raw lat/lon, since a terminal has no
map to click on.

## Design

| Class            | Responsibility                                              |
|-------------------|--------------------------------------------------------------|
| `GeoPoint`         | Plain lat/lon pair                                          |
| `User`             | A simulated nearby account                                  |
| `Bounty`           | A posted lost item/pet with radius, reward, and status       |
| `Claim`            | A finder's submission against a bounty                      |
| `LedgerEntry`      | An immutable record of a released escrow split               |
| `GeoBountyPlatform`| Owns all state; encapsulates the post -> broadcast -> claim -> approve -> ledger flow |

`haversineKm()` and `splitReward()` are free functions with no class dependencies,
mirroring `geo_utils.py` in the Streamlit version so the core logic is easy to compare
side by side across both prototypes.

## Notes

- This is a single-process, single-session simulation -- state resets when you exit.
- Anti-fraud (photo/geotag verification) and real push notifications are out of scope
  here, same as in the Streamlit prototype -- see the top-level README for the full
  list of simplifications and the production roadmap.
