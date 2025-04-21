import streamlit as st
import plotly.graph_objects as go
import random

# --- PAGE CONFIG ---
st.set_page_config(page_title="MGA Dashboard", layout="wide")

# --- TITLE ---
st.title("📊 MGA Dashboard")

# --- INITIAL ENERGY DATA ---
initial_energy_sources = {
    "PV": {"min": 40, "max": 60, "value": 47},
    "Wind": {"min": 40, "max": 60, "value": 55},
    "Coal": {"min": 30, "max": 60, "value": 45},
    "Nuclear": {"min": 20, "max": 60, "value": 40},
    "Gas CHP": {"min": 20, "max": 60, "value": 30}
}

# --- SESSION STATE INIT ---
if "priority_order" not in st.session_state:
    st.session_state.priority_order = list(initial_energy_sources.keys())

if "energy_sources" not in st.session_state:
    st.session_state.energy_sources = {
        k: v.copy() for k, v in initial_energy_sources.items()
    }

if "slider_constraints" not in st.session_state:
    st.session_state.slider_constraints = {}

if "limiters_initialized" not in st.session_state:
    st.session_state.limiters_initialized = False

# --- MAIN LAYOUT ---
left_col, right_col = st.columns([1, 2])

# --- LEFT COLUMN ---
with left_col:
    with st.container():
        st.subheader("🔋 Energy Source Controls & Priority")

        # --- RESET BUTTON ---
        if st.button("🔄 Reset to Initial"):
            st.session_state.priority_order = list(initial_energy_sources.keys())
            st.session_state.energy_sources = {
                k: v.copy() for k, v in initial_energy_sources.items()
            }
            st.session_state.slider_constraints = {}
            st.session_state.limiters_initialized = False
            st.experimental_rerun()

        for i, source in enumerate(st.session_state.priority_order):
            energy_data = st.session_state.energy_sources[source]
            val = energy_data["value"]
            min_val = energy_data["min"]
            max_val = energy_data["max"]
            pct = int(((val - min_val) / (max_val - min_val)) * 100)

            cols = st.columns([0.1, 0.15, 0.75])

            with cols[0]:
                if st.button("⬆️", key=f"up_{source}") and i > 0:
                    st.session_state.priority_order[i], st.session_state.priority_order[i - 1] = (
                        st.session_state.priority_order[i - 1],
                        st.session_state.priority_order[i],
                    )
                    st.rerun()
                if st.button("⬇️", key=f"down_{source}") and i < len(st.session_state.priority_order) - 1:
                    st.session_state.priority_order[i], st.session_state.priority_order[i + 1] = (
                        st.session_state.priority_order[i + 1],
                        st.session_state.priority_order[i],
                    )
                    st.rerun()

            with cols[1]:
                st.markdown(f"**{source}**")

            with cols[2]:
                action = st.radio(
                    label="",
                    options=["🔼", "⏸️", "🔽"],
                    index=["🔼", "⏸️", "🔽"].index(
                        st.session_state.get(f"{source}_action", "⏸️")
                    ),
                    key=f"{source}_action",
                    horizontal=True
                )

                # --- CUSTOM HOVER PROGRESS BAR ---
                progress_html = f"""
                <div style="position: relative; height: 24px; background-color: #e0e0e0; border-radius: 8px; overflow: hidden;">
                    <div style="width: {pct}%; height: 100%; background-color: #1f77b4;"></div>
                    <div style="
                        position: absolute;
                        top: 0;
                        left: 0;
                        width: 100%;
                        height: 100%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        opacity: 0;
                        transition: opacity 0.3s;
                        font-weight: bold;
                        color: #000;
                        background-color: rgba(255, 255, 255, 0.7);
                    " class="hover-text">
                        {val} GW / {min_val} GW - {max_val} GW
                    </div>
                </div>
                <style>
                    .hover-text:hover {{
                        opacity: 1 !important;
                    }}
                </style>
                """
                st.markdown(progress_html, unsafe_allow_html=True)

            st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)

    with st.container():
        st.subheader("📬 Message Box")
        message = "Use the ↑ and ↓ buttons to reorder energy sources.\nThe slider below reflects the top priority source."
        if st.session_state.slider_constraints:
            for reason, limit in st.session_state.slider_constraints.items():
                message += f"\n⚠️ Limited by **{reason}** at {limit} GW."
        st.text_area("", value=message, height=150)

# --- RIGHT COLUMN ---
with right_col:
    with st.container():
        st.subheader("📈 Plot")

        # Smaller dropdown layout
        select_col, _ = st.columns([0.3, 1.7])
        with select_col:
            scenario = st.selectbox("", ["New Capacity", "Emissions", "Cost"])

        user_input = {key: st.session_state.energy_sources[key]["value"] for key in st.session_state.energy_sources}
        baseline = {key: 50 for key in st.session_state.energy_sources}

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=list(user_input.keys()),
            y=list(user_input.values()),
            name='User Scenario',
            marker_color='blue'
        ))
        fig.add_trace(go.Bar(
            x=list(baseline.keys()),
            y=list(baseline.values()),
            name='Baseline Scenario',
            marker_color='lightgray'
        ))
        fig.update_layout(
            barmode='group',
            title=f"{scenario} Comparison",
            yaxis_title="Capacity (GW)" if scenario == "New Capacity" else "Value",
            xaxis_title="Technology",
            height=500
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    with st.container():
        # --- SLIDER FOR TOP PRIORITY ENERGY SOURCE ---
        top_source = st.session_state.priority_order[0]
        top_data = st.session_state.energy_sources[top_source]
        top_action = st.session_state.get(f"{top_source}_action", "⏸️")

        default_min = top_data["min"]
        default_max = top_data["max"]
        current_val = top_data["value"]
        disabled = (top_action == "⏸️")

        # No limiters on first interaction
        limiters = {}

        # If interaction has occurred before, apply constraints
        if st.session_state.limiters_initialized:
            others = [src for src in st.session_state.energy_sources if src != top_source]
            chosen = random.sample(others, 2)
            limits = sorted(random.sample(range(default_min, default_max), 2))
            limiters = dict(zip(chosen, limits))
            st.session_state.slider_constraints = limiters

            if top_action == "🔼":
                max_limit = min(limits)
                default_max = min(default_max, max_limit)
            elif top_action == "🔽":
                min_limit = max(limits)
                default_min = max(default_min, min_limit)

        # --- SLIDER ---
        st.subheader(f"🔧 {top_source}")
        new_val = st.slider(
            f"{top_source} Capacity (GW)",
            min_value=default_min,
            max_value=default_max,
            value=current_val,
            step=1,
            disabled=disabled,
            key=f"{top_source}_slider"
        )

        # Update flag on first change
        if not disabled and not st.session_state.limiters_initialized and new_val != current_val:
            st.session_state.limiters_initialized = True
            st.rerun()

        # Update slider value in session
        if not disabled:
            st.session_state.energy_sources[top_source]["value"] = new_val

        # --- Render Limiters ---
        if st.session_state.limiters_initialized and not disabled:
            slider_range = default_max - default_min
            st.markdown("<div style='position: relative; height: 14px; background: #ddd; border-radius: 4px; margin-bottom: 30px;'>", unsafe_allow_html=True)
            for reason, val in st.session_state.slider_constraints.items():
                if default_min <= val <= default_max:
                    left_pct = int(((val - default_min) / slider_range) * 100)
                    st.markdown(
                        f"""
                        <div style="
                            position: absolute;
                            left: {left_pct}%;
                            width: 4px;
                            height: 24px;
                            background-color: red;
                            top: -6px;
                            border-radius: 2px;
                        " title="Limited by {reason} at {val} GW"></div>
                        <div style="
                            position: absolute;
                            left: calc({left_pct}% - 12px);
                            top: 24px;
                            font-size: 12px;
                            color: red;
                        ">{val} GW</div>
                        """,
                        unsafe_allow_html=True
                    )
            st.markdown("</div>", unsafe_allow_html=True)


