import streamlit as st
import numpy as np
import pandas as pd
import uuid
import json, ast
import base64
from pathlib import Path
from gurobipy import Model, GRB, quicksum
import plotly.graph_objects as go

# --- Page config (first command) ---
st.set_page_config(page_title="MGA Dashboard (Dynamic MGA)", layout="wide")

# --- Encode logos as Base64 ---
def img_to_base64(path: str) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode()

tu_b64   = img_to_base64("TU_Darmstadt_Logo.png")
eins_b64 = img_to_base64("EINS logo.png")

# --- Header HTML for pixel-perfect layout ---
header_html = f"""
<div style="
  border-top:5px solid #007398;
  border-bottom:5px solid #007398;
  padding:1rem 0;
">
  <div style="display:flex; justify-content:center; gap:3rem; margin-bottom:1rem;">
    <img src="data:image/png;base64,{tu_b64}" width="180"/>
    <img src="data:image/png;base64,{eins_b64}" width="180"/>
  </div>
  <div style="text-align:center;">
    <h2 style="margin:0; font-family:inherit; color:#111;">
      Welcome to the Energy Information Networks &amp; Systems (EINS) MGA Dashboard
    </h2>
  </div>
</div>
"""
st.markdown(header_html, unsafe_allow_html=True)

# --- Progress‐bar CSS ---
st.markdown("""
    <style>
    .pcont { position:relative; height:20px; background:#eee; border-radius:10px; margin-top:0.5rem; }
    .pfill { height:100%; background:#007398; border-radius:10px; }
    .tt { visibility:hidden; opacity:0; position:absolute; top:-28px; left:50%;
          transform:translateX(-50%); background:black; color:white; padding:4px 8px;
          border-radius:4px; font-size:14px; white-space:nowrap; transition:opacity .3s;
          z-index:10; }
    .pcont:hover .tt { visibility:visible; opacity:1; }
    </style>
""", unsafe_allow_html=True)

# --- Core configuration & data loading ---
default_sources = ["PV", "Wind", "Coal", "Nuclear", "Gas CHP"]
ϵ = 0.02

@st.cache_data
def load_feasible_region():
    df = pd.read_excel("A_matrix_feasible_region.xlsx")
    return {col: df[col].values for col in df.columns}

@st.cache_data
def load_precomputed_mga_paths():
    raw = json.load(open("precomputed_mga_nested.json"))
    return {ast.literal_eval(k): v for k, v in raw.items()}

A = load_feasible_region()
_ = load_precomputed_mga_paths()
A_np = np.array([A[s] for s in default_sources])
UB   = {s: A_np[i].max() for i,s in enumerate(default_sources)}
LB   = {s: A_np[i].min() for i,s in enumerate(default_sources)}
R    = {s: UB[s] - LB[s] for s in default_sources}

@st.cache_data
def generate_ts_data():
    years = np.arange(2030, 2061)
    n     = len(years)
    pv    = np.linspace(50,200,n) + np.random.normal(0,5,n)
    wind  = np.linspace(75,200,n) + np.random.normal(0,5,n)
    coal  = np.clip(np.linspace(100,0,n)+np.random.normal(0,3,n),0,None)
    nuclear = np.zeros(n)
    nuclear[:6] = np.linspace(20,0,6)
    nuclear = np.clip(nuclear + np.random.normal(0,1,n),0,None)
    gas   = np.clip(np.linspace(30,60,n)+np.random.normal(0,2,n),0,None)
    return pd.DataFrame({"PV":pv,"Wind":wind,"Coal":coal,
                         "Nuclear":nuclear,"Gas CHP":gas},
                        index=years)

ts_data  = generate_ts_data()
ts_means = ts_data.mean()

# --- Solver & constraint logic ---
def solve_lp(constraints, obj_source, maximize=False):
    m = Model(); m.setParam("OutputFlag",0)
    n = len(A[default_sources[0]])
    λ = m.addVars(n, lb=0, ub=1)
    m.addConstr(quicksum(λ[j] for j in range(n)) == 1)
    m.setObjective(quicksum(A[obj_source][j]*λ[j] for j in range(n)),
                   GRB.MAXIMIZE if maximize else GRB.MINIMIZE)
    for src,(lb,ub) in constraints.items():
        expr = quicksum(A[src][j]*λ[j] for j in range(n))
        if lb is not None: m.addConstr(expr >= lb)
        if ub is not None: m.addConstr(expr <= ub)
    m.optimize()
    if m.status == GRB.OPTIMAL:
        vals = np.array([λ[j].X for j in range(n)])
        return {s: float(vals.dot(A[s])) for s in default_sources}
    return None

def gen_step_constraint(prev_pt, src, direction, use_slider_val=None):
    if use_slider_val is not None:
        if direction=="↑": return (min(use_slider_val+ϵ*R[src],UB[src]), None)
        if direction=="↓": return (None, max(use_slider_val-ϵ*R[src],LB[src]))
        return (max(use_slider_val-ϵ*R[src],LB[src]), min(use_slider_val+ϵ*R[src],UB[src]))
    if direction=="↑": return (min(prev_pt[src]+ϵ*R[src],UB[src]), None)
    if direction=="↓": return (None, max(prev_pt[src]-ϵ*R[src],LB[src]))
    return (max(prev_pt[src]-ϵ*R[src],LB[src]), min(prev_pt[src]+ϵ*R[src],UB[src]))

# --- Callbacks ---
def on_dir_change(src):
    k = st.session_state.current_step
    dirc = st.session_state[f"dir_{k}"]
    st.session_state.user_directions[src] = dirc
    base = dict(st.session_state.constraints)
    if dirc in ("↑","↓"):
        sol = solve_lp(base, obj_source=src, maximize=(dirc=="↑"))
        st.session_state.next_point = sol or {}
        st.session_state.message    = "🟢 Extreme found. Slide to explore!" if sol else "⚠️ No feasible extreme."
        return
    lb, ub = gen_step_constraint(st.session_state.current_point, src, dirc)
    base[src] = (lb, ub)
    sol = solve_lp(base, obj_source=st.session_state.priority_order[k])
    st.session_state.next_point = sol or {}
    st.session_state.message    = "🟢 Drag slider then ▶" if sol else "⚠️ No feasible point."

def on_proceed():
    k   = st.session_state.current_step
    src = st.session_state.priority_order[k]
    dirc = st.session_state[f"dir_{k}"]
    val = st.session_state[f"slide_{k}"]
    lb, ub = gen_step_constraint(st.session_state.current_point, src, dirc, use_slider_val=val)
    st.session_state.constraints[src] = (lb, ub)
    sol = solve_lp(st.session_state.constraints, obj_source=src)
    if sol:
        st.session_state.current_point = sol
        st.session_state.current_step += 1
        st.session_state.message = f"🔒 Locked {src} at {val:.1f} GW"
        return True
    st.session_state.message = "❌ Locked infeasible!"
    return False

# --- Session initialization ---
if "priority_order"  not in st.session_state: st.session_state.priority_order  = default_sources.copy()
if "current_point"   not in st.session_state:
    init = np.full(len(A[default_sources[0]]),1/len(A[default_sources[0]]))
    st.session_state.current_point = {s:float(init.dot(A[s])) for s in default_sources}
if "constraints"     not in st.session_state: st.session_state.constraints     = {}
if "current_step"    not in st.session_state: st.session_state.current_step    = 0
if "user_directions" not in st.session_state: st.session_state.user_directions = {}
if "next_point"      not in st.session_state: st.session_state.next_point      = dict(st.session_state.current_point)
if "message"         not in st.session_state: st.session_state.message         = "Pick a direction to see the new extreme."
if "slider_values"   not in st.session_state: st.session_state.slider_values   = {}

# --- Main Layout ---
left, right = st.columns([1,2], gap="large")

with left:
    st.subheader("🔋 Energy Controls & Priority")
    if st.button("🔄 Reset"):
        for k in ["priority_order","current_point","constraints",
                  "current_step","user_directions","next_point",
                  "message","slider_values"]:
            st.session_state.pop(k, None)
        st.rerun()

    for i, src in enumerate(st.session_state.priority_order, start=1):
        po = st.session_state.priority_order
        c1, c2, c3 = st.columns([0.15,0.3,0.55])
        cur = st.session_state.current_point[src]
        lo, hi = LB[src], UB[src]
        pct = int((cur - lo)/(hi - lo)*100)

        with c1:
            if st.button("⬆️", key=f"up_{src}") and i>1:
                po[i-1], po[i-2] = po[i-2], po[i-1]; st.rerun()
            if st.button("⬇️", key=f"down_{src}") and i<len(po):
                po[i-1], po[i]   = po[i], po[i-1]; st.rerun()

        with c2:
            st.markdown(f"**{i}. {src}** – {cur:.1f} GW")

        with c3:
            uid = f"prog_{uuid.uuid4().hex}"
            tip = f"{cur:.1f} GW ({lo:.1f}–{hi:.1f})"
            st.markdown(f"""
                <div id="{uid}" class="pcont">
                  <div class="tt">{tip}</div>
                  <div class="pfill" style="width:{pct}%"></div>
                </div>
            """, unsafe_allow_html=True)

    k = st.session_state.current_step
    if k < len(st.session_state.priority_order):
        src = st.session_state.priority_order[k]
        st.divider()
        st.subheader(f"🎯 Step {k+1}: Set direction for **{src}**")
        idx = ["↑","⏸️","↓"].index(st.session_state.user_directions.get(src,"⏸️"))
        st.radio("Direction", ["↑","⏸️","↓"], index=idx,
                 key=f"dir_{k}", horizontal=True,
                 on_change=lambda s=src: on_dir_change(s))

        if src in st.session_state.user_directions:
            lo, hi = st.session_state.current_point[src], st.session_state.next_point[src]
            if hi < lo: lo, hi = hi, lo
            val = st.slider(
                f"{src} capacity",
                min_value=float(lo),
                max_value=float(hi),
                value=float(hi),
                step=(hi - lo)/100 if hi != lo else 0.0,
                key=f"slide_{k}"
            )
            st.session_state.slider_values[f"slide_{k}"] = val

        if st.button("➡️ Proceed to Step", key=f"next_{k}") and on_proceed():
            st.rerun()

        st.text_area("", value=st.session_state.message, height=100)
    else:
        st.success("✅ All priorities done!")

with right:
    # 1) Capacity Projections
    st.subheader("📆 Capacity Projections (2030–2060)")
    cp     = st.session_state.current_point
    ratios = {s: cp[s]/ts_means[s] for s in default_sources}
    df_plot = ts_data.mul(pd.Series(ratios), axis=1)
    fig_ts  = go.Figure()
    for s in df_plot.columns:
        fig_ts.add_trace(go.Scatter(x=df_plot.index, y=df_plot[s], name=s))
    fig_ts.update_layout(xaxis_title="Year", yaxis_title="Capacity (GW)", height=300)
    st.plotly_chart(fig_ts, use_container_width=True)

    # 2) Interpolated Energy Values
    st.subheader("📈 Interpolated Energy Values")
    k = st.session_state.current_step
    if k < len(st.session_state.priority_order) and f"slide_{k}" in st.session_state:
        src = st.session_state.priority_order[k]
        lo, hi = st.session_state.current_point[src], st.session_state.next_point[src]
        α = 0 if hi == lo else (st.session_state[f"slide_{k}"] - lo)/(hi - lo)
        interp = {
            s: (1-α)*st.session_state.current_point[s] + α*st.session_state.next_point[s]
            for s in default_sources
        }
    else:
        interp = st.session_state.current_point

    fig = go.Figure([go.Bar(
        x=list(interp.keys()),
        y=list(interp.values()),
        marker_color="#007398"
    )])
    fig.update_layout(
        title="Convex Interpolated Feasible Point",
        xaxis_title="Energy Source",
        yaxis_title="Capacity (GW)",
        height=400
    )
    st.plotly_chart(fig, use_container_width=True)

    # 3) Your Selections
    st.subheader("📝 Your Selections")
    records = [
        {"Source": src,
         "Direction": st.session_state.user_directions.get(src,""),
         "Slider Value (GW)": st.session_state.slider_values.get(f"slide_{i}","")}
        for i, src in enumerate(st.session_state.priority_order)
    ]
    st.dataframe(pd.DataFrame(records), use_container_width=True)

    # 4) Credits
    st.markdown(
        "<div style='text-align:right; font-size:1.2em; color:gray; margin-top:1rem;'>"
        "Created by: Muhammad Fazeel<br>"
        "Supervisors: Prof. Dr. Florian Steinke, Sina Hajikazemi"
        "</div>",
        unsafe_allow_html=True
    )
