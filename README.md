[README.md](https://github.com/user-attachments/files/30637697/README.md)
#  Find & Reward -- Crowdsourced Geo-Bounty App

Post a lost item or pet, pay to broadcast it to nearby users within a radius you choose,
and reward whoever finds it. The reward is split between the finder and the platform and
held in escrow until a verified handshake.

This repo contains two independent, fully-working prototypes of the same core idea:

| Prototype | Stack | What it is |
|---|---|---|
| [`streamlit_app/`](streamlit_app) | Python + Streamlit + Folium + SQLite | An interactive web app -- click a map to post a bounty, watch the broadcast radius simulate who gets notified, submit/approve claims, and see escrow payouts land in a ledger. |
| [`cpp_simulation/`](cpp_simulation) | C++17, standard library only | The same post → broadcast → claim → approve → ledger flow as an object-oriented terminal program, with zero dependencies. |

Both implement the same core algorithm independently -- **Haversine distance** for radius
filtering and a **reward split on claim approval** -- so you can compare `geo_utils.py`
against the free functions at the top of `cpp_simulation/main.cpp` to see the logic itself,
decoupled from either language's framework.

## Contents

- [Features](#features)
- [Quick start](#quick-start)
- [Running the Streamlit web app](#running-the-streamlit-web-app)
- [Running the C++ CLI simulation](#running-the-c-cli-simulation)
- [Troubleshooting](#troubleshooting)
- [How it works](#how-it-works)
- [Repository structure](#repository-structure)
- [Design notes & known simplifications](#design-notes--known-simplifications)
- [Path to production](#path-to-production)

## Features

-  Click-to-post a bounty on an interactive map (Streamlit version)
-  Simulated push-notification broadcast, filtered by real Haversine distance
-  Escrow-style reward flow: post → fund → claim → approve → split → release
-  Auditable escrow ledger of every payout
-  Two independent implementations (Python web app / C++ CLI) of the same logic

## Quick start

```bash
git clone https://github.com/<your-username>/geo-bounty.git
cd geo-bounty
```

Then jump to whichever prototype you want to run below.

## Running the Streamlit web app

**Requires:** Python 3.9+

```bash
cd streamlit_app
pip install -r requirements.txt
streamlit run app.py
```

This opens automatically at `http://localhost:8501`. On first run it creates a local
`geo_bounty.db` SQLite file and seeds ~30 demo users around Mumbai so the broadcast
simulation has something to filter against.

> **On Windows**, if `pip` or `streamlit` aren't recognized as commands, use the Python
> launcher instead:
> ```powershell
> py -m pip install -r requirements.txt
> py -m streamlit run app.py
> ```

**Demo walkthrough:**
1. **Post a Bounty** -- click the map to drop a pin, describe what was lost, set a radius and reward.
2. **Live Map & Broadcast** -- see which demo users fall inside the paid radius (green = notified, grey = not).
3. **Resolve Claims** -- submit a "found it" claim, then approve or reject it.
4. **Escrow Ledger** -- every payout ever released, with running totals.

## Running the C++ CLI simulation

**Requires:** a C++17 compiler (g++ or clang)

```bash
cd cpp_simulation
g++ -std=c++17 -O2 -o geobounty main.cpp
./geobounty
```

On Windows, run this inside WSL, or compile with MSVC / MinGW if you have it set up.

It seeds 16 demo users at reproducible random points around Mumbai, then drops you into
a numbered menu to post a bounty, simulate a broadcast, submit/resolve claims, and view
the escrow ledger.

## Troubleshooting

<details>
<summary><code>pip</code> / <code>streamlit</code> is not recognized (Windows)</summary>

Python's `Scripts` folder usually isn't on PATH by default. Use the launcher instead:
```powershell
py -m pip install -r requirements.txt
py -m streamlit run app.py
```
</details>

<details>
<summary>Port 8501 already in use</summary>

Another Streamlit app (or a previous run) is still using the port. Either close it, or run:
```bash
streamlit run app.py --server.port 8502
```
</details>

<details>
<summary><code>ModuleNotFoundError: No module named 'streamlit'</code></summary>

The install step didn't run, or ran against a different Python than the one launching the
app. Re-run `pip install -r requirements.txt` (or `py -m pip install -r requirements.txt`
on Windows) from inside the `streamlit_app` folder, then relaunch.
</details>

<details>
<summary>C++: <code>'g++' is not recognized</code></summary>

You don't have a C++ compiler on PATH. On Windows, install it via WSL
(`sudo apt install g++`) or MSYS2/MinGW; on macOS, run `xcode-select --install`;
on Linux, `sudo apt install g++` (Debian/Ubuntu) or your distro's equivalent.
</details>

## How it works

- **Distance:** the Haversine formula computes the great-circle distance between a
  bounty's last-known location and every candidate user's location.
- **Radius filtering:** a user is "notified" only if `distance <= paid_radius`.
- **Escrow:** the reward is conceptually locked when a bounty is posted. On a verified
  claim it's split -- 50% to the finder / 50% platform fee by default, adjustable per
  bounty -- and recorded as an immutable ledger entry. Approving one claim auto-rejects
  any other pending claims on that bounty.

## Repository structure

```
geo-bounty/
├── README.md                  <- you are here
├── .gitignore
├── streamlit_app/
│   ├── app.py                  Streamlit UI (post / map / resolve / ledger tabs)
│   ├── geo_utils.py             Haversine, radius filter, reward split (pure functions)
│   ├── database.py              SQLite persistence + escrow flow
│   ├── requirements.txt
│   └── README.md                Streamlit-specific docs
└── cpp_simulation/
    ├── main.cpp                 OOP CLI simulation, same logic in C++
    └── README.md                 C++-specific docs
```

## Design notes & known simplifications

This is a **portfolio prototype**, not a production system. A few things are intentionally
simplified, and called out here rather than glossed over:

- **Perverse incentives** -- nothing stops someone from taking an item and "finding" it
  for the reward. A real system needs geotagged photo proof, reputation tracking, and a
  reporting/review flow before payout; this prototype models the escrow *mechanics* only.
- **Safety scope** -- deliberately limited to **items and pets**. Missing-person listings
  are excluded to avoid enabling stalking or vigilante searches for people.
- **Cold start** -- the broadcast mechanic only works with enough nearby users. Both
  prototypes sidestep this by seeding random simulated users; a real launch would need a
  density strategy (e.g. neighborhood-by-neighborhood rollout).
- Users are simulated random points, not real device GPS.
- Photo proof is a free-text note, not real image + geotag verification.
- No authentication -- anyone can act as "the poster" or "a finder" by typing a name.

## Path to production

| Layer | Prototype | Production target |
|---|---|---|
| Frontend | Streamlit | Flutter (iOS/Android) |
| Backend | In-process Python | FastAPI (Python) or Node.js/TypeScript |
| Database | SQLite | PostgreSQL + PostGIS (spatial indexing) |
| Notifications | Map visualization | Real push (FCM/APNs) |
| Anti-fraud | Text proof note | Geotagged photo verification + report/review pipeline |
| Payments | Local ledger table | Real escrow via a payments/marketplace provider |

[Download Project ZIP Archive](https://github.com/kalafrog/lost-and-found-app/archive/refs/heads/main.zip)
