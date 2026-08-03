"""
Find & pet -- crowdsourced geo-bounty prototype
====================================================
Post a lost item or pet, set a paid search radius, and simulate broadcasting
it to nearby users. When someone finds it, the reward is split between the
finder and the platform and released from escrow.

Run locally with:
    pip install -r requirements.txt
    streamlit run app.py
"""

import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium

import database as db
from geo_utils import split_reward

# ----------------------------------------------------------------- setup ---

st.set_page_config(page_title="Find & Reward", page_icon="🧭", layout="wide")

DEFAULT_CENTER = (19.0760, 72.8777)  # Mumbai, used as the demo city center

db.init_db()
db.seed_demo_users(*DEFAULT_CENTER, count=30, spread_km=6.0)

if "map_click" not in st.session_state:
    st.session_state.map_click = None


def money(v: float) -> str:
    return f"\u20b9{v:,.2f}"


# ----------------------------------------------------------------- header --

st.title("🧭 Find & Reward")
st.caption(
    "A crowdsourced geo-bounty prototype -- post what you've lost, pay to broadcast it "
    "to nearby users, and reward whoever finds it. Simulated escrow, simulated push "
    "notifications, real Haversine geometry."
)

tab_post, tab_map, tab_resolve, tab_ledger, tab_about = st.tabs(
    ["📍 Post a Bounty", "🗺️ Live Map & Broadcast", "✅ Resolve Claims", "💰 Escrow Ledger", "ℹ️ About"]
)

# ------------------------------------------------------------ Post a Bounty

with tab_post:
    st.subheader("Post a lost item or pet")
    st.write("Click the map to drop a pin at the last-known location, then fill in the details.")

    left, right = st.columns([3, 2])

    with left:
        post_map = folium.Map(location=DEFAULT_CENTER, zoom_start=12, tiles="CartoDB positron")
        if st.session_state.map_click:
            folium.Marker(
                st.session_state.map_click,
                tooltip="Last known location",
                icon=folium.Icon(color="red", icon="map-pin", prefix="fa"),
            ).add_to(post_map)
        click_result = st_folium(post_map, height=420, width=None, key="post_map")

        if click_result and click_result.get("last_clicked"):
            st.session_state.map_click = (
                click_result["last_clicked"]["lat"],
                click_result["last_clicked"]["lng"],
            )
            st.rerun()

        if st.session_state.map_click:
            st.info(
                f"Pin set at {st.session_state.map_click[0]:.5f}, {st.session_state.map_click[1]:.5f}"
            )
        else:
            st.warning("No pin set yet -- click anywhere on the map above.")

    with right:
        with st.form("post_bounty_form", clear_on_submit=True):
            poster_name = st.text_input("Your name", value="Guest")
            category = st.selectbox("Category", ["item", "pet"], format_func=str.title)
            item_name = st.text_input("What was lost?", placeholder="e.g. Golden Retriever 'Bruno' / Black backpack")
            description = st.text_area(
                "Description", placeholder="Distinguishing details: color, markings, where/when last seen..."
            )
            radius_km = st.slider("Paid search radius (km)", 0.5, 10.0, 2.0, 0.5)
            reward_total = st.number_input("Total reward (₹)", min_value=50, max_value=100000, value=500, step=50)
            finder_pct = st.slider("Finder's share of reward (%)", 0, 100, 50, 5)

            finder_share, platform_share = split_reward(reward_total, finder_pct)
            st.caption(f"Finder gets {money(finder_share)} · Platform fee {money(platform_share)}")

            submitted = st.form_submit_button("🔒 Post & fund escrow", use_container_width=True)

            if submitted:
                if not item_name.strip():
                    st.error("Please describe what was lost.")
                elif not st.session_state.map_click:
                    st.error("Please click the map to set a last-known location first.")
                else:
                    lat, lon = st.session_state.map_click
                    bounty_id = db.create_bounty(
                        poster_name or "Guest", category, item_name.strip(), description.strip(),
                        lat, lon, radius_km, float(reward_total), finder_pct,
                    )
                    st.session_state.map_click = None
                    st.success(f"Bounty #{bounty_id} posted and escrow funded with {money(reward_total)}.")
                    st.rerun()

# ----------------------------------------------------------- Live Map tab --

with tab_map:
    st.subheader("Active bounties & simulated broadcast radius")
    active = db.get_bounties(status="active")

    if not active:
        st.info("No active bounties yet -- post one in the previous tab.")
    else:
        options = {f"#{b['id']} -- {b['item_name']}": b["id"] for b in active}
        chosen_label = st.selectbox("Select a bounty to inspect", list(options.keys()))
        chosen_id = options[chosen_label]
        bounty = db.get_bounty(chosen_id)
        targets = db.broadcast_targets(chosen_id)

        col_map, col_info = st.columns([3, 2])

        with col_map:
            m = folium.Map(location=(bounty["lat"], bounty["lon"]), zoom_start=13, tiles="CartoDB positron")
            folium.Marker(
                (bounty["lat"], bounty["lon"]),
                tooltip=bounty["item_name"],
                icon=folium.Icon(color="red", icon="star", prefix="fa"),
            ).add_to(m)
            folium.Circle(
                (bounty["lat"], bounty["lon"]),
                radius=bounty["radius_km"] * 1000,
                color="#D97757",
                fill=True,
                fill_opacity=0.08,
                tooltip=f"Paid broadcast radius: {bounty['radius_km']} km",
            ).add_to(m)
            for u in targets:
                folium.CircleMarker(
                    (u["lat"], u["lon"]),
                    radius=6,
                    color="#2b7a3e",
                    fill=True,
                    fill_opacity=0.9,
                    tooltip=f"{u['name']} -- {u['distance_km']} km away (notified)",
                ).add_to(m)
            all_users = db.get_users()
            outside = [u for u in all_users if u["id"] not in {t["id"] for t in targets}]
            for u in outside:
                folium.CircleMarker(
                    (u["lat"], u["lon"]),
                    radius=4,
                    color="#999999",
                    fill=True,
                    fill_opacity=0.5,
                    tooltip=f"{u['name']} -- outside radius (not notified)",
                ).add_to(m)
            st_folium(m, height=460, width=None, key=f"view_map_{chosen_id}")

        with col_info:
            st.markdown(f"### {bounty['item_name']}")
            st.write(bounty["description"] or "_No description provided._")
            st.write(f"**Category:** {bounty['category'].title()}")
            st.write(f"**Reward:** {money(bounty['reward_total'])} ({bounty['finder_pct']}% to finder)")
            st.write(f"**Radius:** {bounty['radius_km']} km")
            st.write(f"**Posted by:** {bounty['poster_name']}")
            st.metric("Users notified by simulated broadcast", len(targets))

            with st.expander("Notified users (nearest first)"):
                if targets:
                    st.dataframe(
                        pd.DataFrame(targets)[["name", "distance_km"]].rename(
                            columns={"name": "User", "distance_km": "Distance (km)"}
                        ),
                        hide_index=True, use_container_width=True,
                    )
                else:
                    st.write("No demo users currently fall inside this radius.")

            if st.button("🚫 Cancel this bounty", key=f"cancel_{chosen_id}"):
                db.cancel_bounty(chosen_id)
                st.rerun()

# --------------------------------------------------------- Resolve Claims --

with tab_resolve:
    st.subheader("Submit and resolve 'found it' claims")

    active = db.get_bounties(status="active")
    if not active:
        st.info("No active bounties to claim right now.")
    else:
        options = {f"#{b['id']} -- {b['item_name']}": b["id"] for b in active}
        chosen_label = st.selectbox("Bounty", list(options.keys()), key="resolve_select")
        chosen_id = options[chosen_label]

        with st.form("claim_form", clear_on_submit=True):
            st.write("**Simulate a finder submitting proof**")
            finder_name = st.text_input("Finder's name")
            proof_note = st.text_area(
                "Proof note", placeholder="Describe the geotagged photo / handoff details a real app would attach here."
            )
            claim_submitted = st.form_submit_button("Submit claim")
            if claim_submitted:
                if not finder_name.strip():
                    st.error("Enter the finder's name.")
                else:
                    db.submit_claim(chosen_id, finder_name.strip(), proof_note.strip())
                    st.success("Claim submitted -- pending owner verification below.")
                    st.rerun()

        st.divider()
        st.write("**Pending claims on this bounty**")
        claims = [c for c in db.get_claims(chosen_id) if c["status"] == "pending"]
        if not claims:
            st.caption("No pending claims.")
        for c in claims:
            with st.container(border=True):
                cols = st.columns([3, 1, 1])
                cols[0].write(f"**{c['finder_name']}** -- {c['proof_note'] or '_no note_'}")
                if cols[1].button("✅ Approve", key=f"approve_{c['id']}"):
                    result = db.approve_claim(c["id"])
                    st.success(
                        f"Escrow released: {result['finder_name']} gets "
                        f"{money(result['finder_share'])}, platform keeps {money(result['platform_share'])}."
                    )
                    st.rerun()
                if cols[2].button("❌ Reject", key=f"reject_{c['id']}"):
                    db.reject_claim(c["id"])
                    st.rerun()

        st.caption(
            "⚠️ Anti-fraud note: a production version requires geotagged photo proof "
            "matched against the bounty location/time before a claim can even be submitted, "
            "plus reporting tools -- this prototype models the escrow mechanics, not the fraud checks."
        )

# ------------------------------------------------------------------ Ledger --

with tab_ledger:
    st.subheader("Escrow ledger")
    ledger = db.get_ledger()
    if not ledger:
        st.info("No resolved bounties yet -- approve a claim to see a payout here.")
    else:
        df = pd.DataFrame(ledger)[
            ["id", "bounty_id", "finder_name", "finder_share", "platform_share", "released_at"]
        ].rename(columns={
            "id": "Ledger ID", "bounty_id": "Bounty #", "finder_name": "Finder",
            "finder_share": "Finder Payout (₹)", "platform_share": "Platform Fee (₹)",
            "released_at": "Released At (UTC)",
        })
        st.dataframe(df, hide_index=True, use_container_width=True)
        c1, c2 = st.columns(2)
        c1.metric("Total paid to finders", money(df["Finder Payout (₹)"].sum()))
        c2.metric("Total platform fees", money(df["Platform Fee (₹)"].sum()))

# -------------------------------------------------------------------- About

with tab_about:
    st.subheader("About this prototype")
    st.markdown(
        """
This is a **portfolio prototype** of a crowdsourced geo-bounty app: post a lost item or pet,
pay to broadcast it within a radius, and reward whoever finds it -- with funds held in escrow
until a verified handshake.

**What's real in this build**
- Exact **Haversine distance** calculation for radius filtering
- A working **escrow model**: post → fund → claim → approve → split → release, all recorded in an
  auditable ledger table
- SQLite persistence, so bounties/claims survive a restart

**What's simulated**
- "Push notifications" are visualized as a broadcast radius on the map with demo users
- "Users" are randomly generated points around a city center rather than real installs
- Photo proof is a text note, not an actual geotagged image match

**Why items/pets only:** missing-person listings are intentionally out of scope to avoid
enabling stalking or vigilante searches for people.

**Path to production:** Flutter (mobile) → FastAPI/Node backend → PostgreSQL + PostGIS for
real spatial indexing and radius queries, with a real payments/escrow provider instead of a
local ledger table.
"""
    )
    if st.button("🔄 Reset all demo data"):
        db.reset_all()
        db.seed_demo_users(*DEFAULT_CENTER, count=30, spread_km=6.0)
        st.session_state.map_click = None
        st.success("Demo data reset.")
        st.rerun()
