import streamlit as st
import plotly.graph_objects as go

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

# --- PRIORITY CONTROL REORDERING ---
new_order = st.multiselect(
    "⚙️ Energy Source Priority (drag to reorder)",
    options=list(st.session_state.energy_sources.keys()),
    default=st.session_state.priority_order,
)

if set(new_order) == set(st.session_state.energy_sources.keys()) and len(new_order) == len(st.session_state.energy_sources):
    st.session_state.priority_order = new_order

# --- MAIN LAYOUT ---
left_col, right_col = st.columns([1, 2])  # Layout split: left 1/3, right 2/3

# --- LEFT COLUMN (Top = Energy Controls, Bottom = Message Box) ---
with left_col:
    with st.container():
        st.subheader("🔋 Energy Source Controls")
        for source in st.session_state.priority_order:
            energy_data = st.session_state.energy_sources[source]
            val = energy_data["value"]
            min_val = energy_data["min"]
            max_val = energy_data["max"]
            pct = int(((val - min_val) / (max_val - min_val)) * 100)

            with st.container():
                st.markdown(f"**{source}**", help="Priority control")
                st.radio(
                    label="Action",
                    options=["🔼 Increase", "➖ Hold", "🔽 Decrease"],
                    index=["🔼 Increase", "➖ Hold", "🔽 Decrease"].index(
                        st.session_state.get(f"{source}_action", "➖ Hold")
                    ),
                    key=f"{source}_action",
                    horizontal=True
                )

                # Display the progress bar with current, minimum, and maximum values
                st.progress(pct, text=f"{val} GW / {min_val} GW - {max_val} GW")

    st.markdown("---")

    with st.container():
        st.subheader("📬 Message Box")
        st.text_area(
            "System Message",
            value="Reorder energy sources and set action per source.\nThe slider reflects the top priority energy source.",
            height=120
        )

# --- RIGHT COLUMN (Top = Graph, Bottom = Slider) ---
with right_col:
    with st.container():
        scenario = st.selectbox("Scenario View", ["New Capacity", "Emissions", "Cost"])

        user_input = {key: st.session_state.energy_sources[key]["value"] for key in st.session_state.energy_sources}
        baseline = {key: 50 for key in st.session_state.energy_sources}

        st.subheader("📈 Scenario Comparison")
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
        top_action = st.session_state.get(f"{top_source}_action", "➖ Hold")

        # Default slider range
        slider_min = top_data["min"]
        slider_max = top_data["max"]
        slider_value = top_data["value"]
        slider_disabled = False

        if top_action == "🔼 Increase":
            slider_min = slider_value
        elif top_action == "🔽 Decrease":
            slider_max = slider_value
        elif top_action == "➖ Hold":
            slider_disabled = True

        st.subheader(f"🔧 Adjust Capacity for Top Priority: {top_source}")
        top_value = st.slider(
            f"{top_source} Capacity (GW)",
            min_value=slider_min,
            max_value=slider_max,
            value=slider_value,
            step=1,
            disabled=slider_disabled,
            key=f"{top_source}_slider"
        )

        if not slider_disabled:
            st.session_state.energy_sources[top_source]["value"] = top_value
