# Find & Reward -- Crowdsourced Geo-Bounty App

**Concept:** post a lost item or pet, pay to broadcast it to nearby users within a
chosen radius, and reward whoever finds it. The reward is split between the finder
and the platform and held in escrow until a verified handshake.

This repo contains two independent prototypes of the same core logic, built for a
portfolio rather than for deployment:

| Prototype | Stack | What it shows |
|---|---|---|
| [`streamlit_app/`](streamlit_app) | Python + Streamlit + Folium + SQLite | An interactive web demo: click a map to post a bounty, see the broadcast radius and which simulated users get notified, submit and approve claims, watch escrow releases land in a ledger. |
| [`cpp_simulation/`](cpp_simulation) | C++17, standard library only | The same post → broadcast → claim → approve → ledger flow as an OOP terminal simulation, useful for showing the core algorithm without any framework in the way. |

Both implement identical core logic independently: **Haversine distance** for radius
filtering and an **escrow split** on claim approval. Comparing `geo_utils.py` against
the free functions at the top of `cpp_simulation/main.cpp` is the fastest way to see
the algorithm itself, decoupled from either language's app-framework boilerplate.

## Quick start

```bash
# Web demo
cd streamlit_app
pip install -r requirements.txt
streamlit run app.py

# CLI demo
cd cpp_simulation
g++ -std=c++17 -O2 -o geobounty main.cpp
./geobounty
```

## Core mechanics

- **Distance:** the Haversine formula gives the great-circle distance between the
  bounty's last-known location and every candidate user's location.
- **Radius filtering:** a user is only "notified" (in this simulation) if
  `distance <= paid_radius`.
- **Escrow:** the full reward is conceptually locked when a bounty is posted. On a
  verified claim, it's split -- by default 50% to the finder, 50% platform fee -- and
  recorded as an immutable ledger entry. All other pending claims on that bounty are
  auto-rejected once one is approved.

## Design challenges this concept has to solve (and how)

- **Perverse incentives** -- someone could take an item and then "find" it for the
  reward. A real system needs fraud checks: geotagged photo proof tied to time/location,
  reputation tracking, and a reporting/review flow before payout. Both prototypes model
  the escrow *mechanics*; neither implements real fraud detection -- that's flagged
  explicitly in the UI/CLI as a gap, not silently glossed over.
- **Safety** -- scope is deliberately restricted to **items and pets only**. Missing-person
  listings are excluded to avoid enabling stalking or vigilante searches for people.
- **Cold start** -- the whole mechanic depends on having enough nearby users to make a
  radius broadcast meaningful. Both prototypes sidestep this for demo purposes by
  seeding random simulated users around a city center; a real launch would need a
  density strategy (e.g. neighborhood-by-neighborhood rollout) before the core loop works.

## Path to production

```
Frontend:     Flutter (iOS/Android)
Backend:      FastAPI (Python) or Node.js/TypeScript
Database:     PostgreSQL + PostGIS (spatial indexing for fast radius queries)
Notifications: Real push (FCM/APNs) instead of a map visualization
Anti-fraud:   Geotagged photo verification + reporting/review pipeline
Payments:     Real escrow via a payments/marketplace provider, not a local ledger table
```

## Repo layout

```
geo-bounty/
├── README.md                 <- you are here
├── streamlit_app/
│   ├── app.py                 Streamlit UI
│   ├── geo_utils.py            Haversine, radius filter, reward split (pure functions)
│   ├── database.py             SQLite persistence + escrow flow
│   ├── requirements.txt
│   └── README.md
└── cpp_simulation/
    ├── main.cpp                OOP CLI simulation, same logic in C++
    └── README.md
```
