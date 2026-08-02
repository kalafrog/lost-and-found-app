# Find & Reward -- Streamlit Prototype

A crowdsourced geo-bounty app: post a lost item or pet, pay to broadcast it to nearby
users within a radius, and reward whoever finds it -- with the payout held in escrow
until a verified handshake.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

Opens at `http://localhost:8501`. A SQLite file (`geo_bounty.db`) is created next to
`app.py` on first run and seeded with ~30 randomly-placed demo users around Mumbai so
the broadcast simulation has something to filter against.

## Demo walkthrough

1. **Post a Bounty** -- click the map to drop a pin, describe what was lost, set a
   radius and reward, and submit. This "funds escrow" (recorded in the `bounties` table).
2. **Live Map & Broadcast** -- pick a bounty and see which demo users fall inside the
   paid radius (green markers, actually notified) versus outside it (grey, not notified).
3. **Resolve Claims** -- simulate a finder submitting a claim with a proof note, then
   approve or reject it. Approving splits the reward per the finder/platform percentage
   and writes an entry to the escrow ledger.
4. **Escrow Ledger** -- every payout ever released, with running totals.

## Architecture

```
app.py          Streamlit UI (4 tabs: post / map / resolve / ledger)
geo_utils.py    Pure functions: Haversine distance, radius filtering, reward split
database.py     SQLite persistence: users, bounties, claims, escrow_ledger
```

`geo_utils.py` has no dependency on Streamlit or SQLite, so it's directly reusable
in a backend service. Run `python3 geo_utils.py` on its own for a quick sanity check
of the distance math.

### Data flow

```
Post bounty --> escrow "funded" (bounties.status = active)
     |
     v
Broadcast simulation --> Haversine-filter all demo users by radius
     |
     v
Finder submits claim --> claims.status = pending
     |
     v
Owner approves --> split_reward() --> escrow_ledger row written
                                   --> bounties.status = resolved
                                   --> other pending claims on the bounty auto-rejected
```

## Known simplifications (by design, for a prototype)

- Users are simulated random points, not real device GPS / push tokens.
- Photo proof is a free-text note, not an actual image + geotag verification.
- No auth -- anyone can act as "the poster" or "a finder" by typing a name.
- Single SQLite file, no concurrent-write handling -- fine for a local demo, not for
  production load.

## Path to production

| Layer      | Prototype        | Production target                          |
|------------|-------------------|---------------------------------------------|
| Frontend   | Streamlit         | Flutter (iOS/Android)                        |
| Backend    | In-process Python | FastAPI (Python) or Node.js/TypeScript       |
| Database   | SQLite            | PostgreSQL + PostGIS (spatial indexing)       |
| Notifications | Map visualization | Real push notifications (FCM/APNs)         |
| Anti-fraud | Text proof note   | Geotagged photo verification + report/review flow |
| Payments   | Local ledger table| Real escrow via a payments/marketplace provider |

## Safety note

Missing-**person** listings are intentionally out of scope for this concept -- broadcasting
a person's last-known location to strangers for a cash reward creates real stalking and
vigilante-search risks. The scope is deliberately limited to items and pets.
