"""
ZA Payment Risk Pipeline — Compliance Dashboard
SARB FinSurv cross-border payment monitoring
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import duckdb
import os
import time
from datetime import datetime

st.set_page_config(
    page_title="ZA Payment Risk | Compliance Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    .block-container {
        padding: 2rem 2.5rem 2rem 2.5rem;
        max-width: 1400px;
    }
    #MainMenu, footer, header { visibility: hidden; }
    .page-header {
        border-bottom: 1px solid #e2e8f0;
        padding-bottom: 16px;
        margin-bottom: 24px;
    }
    .page-header h1 {
        font-size: 20px;
        font-weight: 600;
        color: #0f172a;
        margin: 0 0 4px 0;
        letter-spacing: -0.3px;
    }
    .page-header p {
        font-size: 13px;
        color: #64748b;
        margin: 0;
    }
    .kpi-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 18px 20px;
    }
    .kpi-label {
        font-size: 11px;
        font-weight: 600;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        margin-bottom: 6px;
    }
    .kpi-value {
        font-size: 26px;
        font-weight: 700;
        color: #0f172a;
        line-height: 1;
    }
    .kpi-value.alert { color: #dc2626; }
    .kpi-value.warning { color: #d97706; }
    .kpi-value.good { color: #16a34a; }
    .kpi-sub {
        font-size: 11px;
        color: #94a3b8;
        margin-top: 4px;
    }
    .section-label {
        font-size: 12px;
        font-weight: 600;
        color: #374151;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 10px;
        padding-bottom: 6px;
        border-bottom: 1px solid #f1f5f9;
    }
    .alert-row {
        background: #fef2f2;
        border-left: 3px solid #dc2626;
        border-radius: 0 6px 6px 0;
        padding: 10px 14px;
        margin-bottom: 8px;
    }
    .alert-row.high {
        background: #fffbeb;
        border-left-color: #d97706;
    }
    .alert-title {
        font-size: 12px;
        font-weight: 600;
        color: #0f172a;
        margin-bottom: 2px;
    }
    .alert-detail {
        font-size: 11px;
        color: #64748b;
    }
    .sar-tag {
        display: inline-block;
        background: #dc2626;
        color: #fff;
        font-size: 10px;
        font-weight: 700;
        padding: 1px 6px;
        border-radius: 3px;
        margin-left: 6px;
        letter-spacing: 0.3px;
    }
    [data-testid="stSidebar"] {
        background: #f8fafc;
        border-right: 1px solid #e2e8f0;
    }
</style>
""", unsafe_allow_html=True)

DB_PATH = os.getenv(
    "DUCKDB_PATH",
    os.path.expanduser("~/za-payment-risk-pipeline/data/za_payments.duckdb")
)

CHART_TEMPLATE = dict(
    template="plotly_white",
    font=dict(family="Inter, -apple-system, sans-serif", size=11, color="#374151"),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(t=16, b=16, l=16, r=16),
    height=260,
)

RISK_COLOURS = {
    "CRITICAL": "#dc2626",
    "HIGH":     "#d97706",
    "MEDIUM":   "#ca8a04",
    "LOW":      "#16a34a",
}


@st.cache_data(ttl=5)
def load_payments() -> pd.DataFrame:
    try:
        conn = duckdb.connect(DB_PATH, read_only=True)
        df = conn.execute("""
            SELECT
                transaction_id, bank_code, originator_id,
                beneficiary_country, amount_zar, currency,
                bop_category_code, ada_ytd_used, ada_utilisation_pct,
                entity_type, risk_score, risk_band,
                compliance_passed, requires_sar,
                violation_count, warning_count,
                is_critical, is_ada_breached, transaction_at
            FROM main.stg_payments
            ORDER BY transaction_at DESC
        """).df()
        conn.close()
        return df
    except Exception as e:
        st.error(f"Could not connect to database: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=5)
def load_daily_report() -> pd.DataFrame:
    try:
        conn = duckdb.connect(DB_PATH, read_only=True)
        df = conn.execute(
            "SELECT * FROM main.finsurvreport_daily ORDER BY report_date DESC"
        ).df()
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=5)
def load_corridors() -> pd.DataFrame:
    try:
        conn = duckdb.connect(DB_PATH, read_only=True)
        df = conn.execute(
            "SELECT * FROM main.corridor_exposure ORDER BY total_volume_zar DESC"
        ).df()
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


# Sidebar
with st.sidebar:
    st.markdown("**ZA Payment Risk**")
    st.markdown(
        "<span style='font-size:11px;color:#64748b'>SARB FinSurv Compliance Monitor</span>",
        unsafe_allow_html=True,
    )
    st.divider()
    st.markdown(
        "<span style='font-size:11px;font-weight:600;color:#374151'>FILTERS</span>",
        unsafe_allow_html=True,
    )
    bank_options = ["ABSAZAJJ", "FIRNZAJJ", "SBZAZAJJ", "NEDSZAJJ", "INVEZMJJ", "CABLZAJJ"]
    selected_banks = st.multiselect("Bank", options=bank_options, placeholder="All banks")
    selected_bands = st.multiselect(
        "Risk band",
        options=["CRITICAL", "HIGH", "MEDIUM", "LOW"],
        placeholder="All bands",
    )
    show_sar_only = st.checkbox("SAR required only", value=False)
    st.divider()
    auto_refresh = st.toggle("Auto-refresh", value=False)
    st.divider()
    st.markdown(
        "<span style='font-size:11px;font-weight:600;color:#374151'>SERVICES</span>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<span style='font-size:11px;color:#16a34a'>● Kafka</span>&nbsp;&nbsp;"
        "<span style='font-size:11px;color:#16a34a'>● MinIO</span>&nbsp;&nbsp;"
        "<span style='font-size:11px;color:#16a34a'>● Faust</span>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<span style='font-size:11px;color:#16a34a'>● dbt</span>&nbsp;&nbsp;"
        "<span style='font-size:11px;color:#16a34a'>● Airflow</span>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<span style='font-size:10px;color:#94a3b8'>Last updated: "
        f"{datetime.now().strftime('%H:%M:%S')}</span>",
        unsafe_allow_html=True,
    )

# Load data
df    = load_payments()
daily = load_daily_report()
corr  = load_corridors()

if df.empty:
    st.warning("No data available. Run dbt seed && dbt run in the dbt_project directory.")
    st.stop()

if selected_banks:
    df = df[df["bank_code"].isin(selected_banks)]
if selected_bands:
    df = df[df["risk_band"].isin(selected_bands)]
if show_sar_only:
    df = df[df["requires_sar"] == True]

# Page header
st.markdown("""
<div class="page-header">
    <h1>Cross-Border Payment Compliance Dashboard</h1>
    <p>SARB FinSurv monitoring · ADA tracking · Real-time risk scoring · Daily report generation</p>
</div>
""", unsafe_allow_html=True)

# KPIs
total     = len(df)
passed    = int(df["compliance_passed"].sum())
pass_rate = round(passed / total * 100, 1) if total else 0
critical  = int((df["risk_band"] == "CRITICAL").sum())
sar_count = int(df["requires_sar"].sum())
total_vol = df["amount_zar"].sum()

k1, k2, k3, k4, k5 = st.columns(5)

with k1:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">Transactions</div>
        <div class="kpi-value">{total}</div>
        <div class="kpi-sub">In current view</div>
    </div>""", unsafe_allow_html=True)

with k2:
    rate_class = "good" if pass_rate >= 75 else "warning" if pass_rate >= 50 else "alert"
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">Compliance Pass Rate</div>
        <div class="kpi-value {rate_class}">{pass_rate}%</div>
        <div class="kpi-sub">{passed} of {total} passed</div>
    </div>""", unsafe_allow_html=True)

with k3:
    crit_class = "alert" if critical > 0 else "good"
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">Critical Alerts</div>
        <div class="kpi-value {crit_class}">{critical}</div>
        <div class="kpi-sub">Require immediate action</div>
    </div>""", unsafe_allow_html=True)

with k4:
    sar_class = "alert" if sar_count > 0 else "good"
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">SAR Filings Required</div>
        <div class="kpi-value {sar_class}">{sar_count}</div>
        <div class="kpi-sub">Suspicious activity reports</div>
    </div>""", unsafe_allow_html=True)

with k5:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">Total Volume</div>
        <div class="kpi-value">R{total_vol / 1_000_000:.2f}M</div>
        <div class="kpi-sub">South African Rand</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# Transaction feed + Alerts
feed_col, alert_col = st.columns([3, 1])

with feed_col:
    st.markdown('<div class="section-label">Transaction Feed</div>', unsafe_allow_html=True)
    feed = df[[
        "transaction_id", "bank_code", "beneficiary_country",
        "amount_zar", "bop_category_code", "risk_band",
        "risk_score", "compliance_passed", "requires_sar",
    ]].copy()
    feed["amount_zar"]        = feed["amount_zar"].apply(lambda x: f"R{x:,.2f}")
    feed["compliance_passed"] = feed["compliance_passed"].apply(lambda x: "Pass" if x else "Fail")
    feed["requires_sar"]      = feed["requires_sar"].apply(lambda x: "Yes" if x else "-")
    feed.columns = [
        "Transaction ID", "Bank", "Country", "Amount",
        "BOP Code", "Risk Band", "Score", "Status", "SAR"
    ]
    st.dataframe(feed, use_container_width=True, height=340, hide_index=True)

with alert_col:
    st.markdown('<div class="section-label">Active Alerts</div>', unsafe_allow_html=True)
    alerts = df[df["risk_band"].isin(["CRITICAL", "HIGH"])].head(8)
    if alerts.empty:
        st.markdown(
            "<div style='padding:16px;background:#f0fdf4;border-radius:6px;"
            "border:1px solid #bbf7d0;font-size:12px;color:#16a34a'>"
            "No active alerts</div>",
            unsafe_allow_html=True,
        )
    else:
        for _, row in alerts.iterrows():
            css_class = "alert-row" if row["risk_band"] == "CRITICAL" else "alert-row high"
            sar_tag   = '<span class="sar-tag">SAR</span>' if row["requires_sar"] else ""
            st.markdown(f"""
            <div class="{css_class}">
                <div class="alert-title">{row['transaction_id'][-12:]} {sar_tag}</div>
                <div class="alert-detail">
                    {row['bank_code']} · {row['beneficiary_country']} · R{row['amount_zar']:,.0f}<br>
                    Score {row['risk_score']} · {row['violation_count']} violation(s)
                </div>
            </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# Charts
ch1, ch2, ch3 = st.columns(3)

with ch1:
    st.markdown('<div class="section-label">Risk Distribution</div>', unsafe_allow_html=True)
    band_counts = df["risk_band"].value_counts().reindex(
        ["CRITICAL", "HIGH", "MEDIUM", "LOW"], fill_value=0
    ).reset_index()
    band_counts.columns = ["Band", "Count"]
    fig1 = px.bar(
        band_counts, x="Band", y="Count",
        color="Band", color_discrete_map=RISK_COLOURS,
    )
    fig1.update_layout(**CHART_TEMPLATE, showlegend=False)
    fig1.update_traces(marker_line_width=0)
    fig1.update_xaxes(title=None)
    fig1.update_yaxes(title=None, gridcolor="#f1f5f9")
    st.plotly_chart(fig1, use_container_width=True)

with ch2:
    st.markdown('<div class="section-label">Corridor Volume (ZAR)</div>', unsafe_allow_html=True)
    if not corr.empty:
        source = corr.head(8)
        x_col  = "beneficiary_country"
        y_col  = "total_volume_zar"
    else:
        source = (
            df.groupby("beneficiary_country")["amount_zar"]
            .sum().reset_index()
            .sort_values("amount_zar", ascending=False)
            .head(8)
        )
        x_col = "beneficiary_country"
        y_col = "amount_zar"
    fig2 = px.bar(
        source, x=x_col, y=y_col,
        color=y_col,
        color_continuous_scale=[[0, "#bfdbfe"], [1, "#1d4ed8"]],
    )
    fig2.update_layout(**CHART_TEMPLATE, showlegend=False, coloraxis_showscale=False)
    fig2.update_traces(marker_line_width=0)
    fig2.update_xaxes(title=None)
    fig2.update_yaxes(title=None, gridcolor="#f1f5f9")
    st.plotly_chart(fig2, use_container_width=True)

with ch3:
    st.markdown('<div class="section-label">ADA Utilisation (%)</div>', unsafe_allow_html=True)
    ada = df[df["entity_type"] == "INDIVIDUAL"].copy()
    ada["ada_utilisation_pct"] = ada["ada_utilisation_pct"].fillna(0)
    ada["short_id"] = ada["originator_id"].str[-8:]
    colours = [
        "#dc2626" if v > 100 else "#d97706" if v > 85 else "#16a34a"
        for v in ada["ada_utilisation_pct"]
    ]
    fig3 = go.Figure(go.Bar(
        x=ada["short_id"],
        y=ada["ada_utilisation_pct"],
        marker_color=colours,
        marker_line_width=0,
    ))
    fig3.add_hline(y=85,  line_dash="dot", line_color="#d97706", line_width=1)
    fig3.add_hline(y=100, line_dash="dot", line_color="#dc2626", line_width=1)
    fig3.update_layout(**CHART_TEMPLATE)
    fig3.update_xaxes(title=None)
    fig3.update_yaxes(title=None, gridcolor="#f1f5f9", range=[0, 130])
    st.plotly_chart(fig3, use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

# FinSurv daily report
st.markdown('<div class="section-label">SARB FinSurv Daily Report</div>', unsafe_allow_html=True)
if not daily.empty:
    cols_to_show = [
        "report_date", "bank_code", "total_transactions",
        "compliance_pass_rate_pct", "risk_critical_count",
        "sar_required_count", "total_volume_zar", "ada_breach_count",
    ]
    report = daily[cols_to_show].copy()
    report["total_volume_zar"]         = report["total_volume_zar"].apply(lambda x: f"R{x:,.2f}")
    report["compliance_pass_rate_pct"] = report["compliance_pass_rate_pct"].apply(lambda x: f"{x}%")
    report.columns = [
        "Date", "Bank", "Transactions", "Pass Rate",
        "Critical", "SAR Required", "Total Volume", "ADA Breaches",
    ]
    st.dataframe(report, use_container_width=True, hide_index=True)
else:
    st.info("Run dbt run --select marts to populate the FinSurv daily report.")

# Footer
st.markdown("<br>", unsafe_allow_html=True)
st.markdown(
    "<div style='border-top:1px solid #e2e8f0;padding-top:12px;"
    "font-size:11px;color:#94a3b8;display:flex;justify-content:space-between'>"
    "<span>ZA Payment Risk Pipeline · Tshepo Tau</span>"
    "<span>Built for SARB FinSurv compliance demonstration · "
    "<a href='https://github.com/tshepo-tau/za-payment-risk-pipeline' "
    "style='color:#4a90d4;text-decoration:none'>GitHub</a></span>"
    "</div>",
    unsafe_allow_html=True,
)

if auto_refresh:
    time.sleep(5)
    st.rerun()