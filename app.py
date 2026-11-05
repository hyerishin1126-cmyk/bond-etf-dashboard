"""
국채·ETF 혼합형 펀드 백테스팅 대시보드
==========================================
Streamlit Community Cloud 배포용 단일 파일 애플리케이션
- 로그인 인증 (st.secrets 우선, fallback: admin / infinity2026)
- 인터랙티브 파라미터 제어 (사이드바)
- 10년 백테스팅 + TAA 전략 시뮬레이션
- KPI · NAV 차트 · Drawdown · 연도별 수익률 · 엑셀 다운로드
"""

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import date
import io
import warnings

warnings.filterwarnings("ignore")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PAGE CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.set_page_config(
    page_title="국채·ETF 혼합형 펀드 백테스팅",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CUSTOM CSS (모바일 + PC 최적화)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CUSTOM_CSS = """
<style>
[data-testid="stMetric"] {
    background: #f8f9fa;
    border: 1px solid #dee2e6;
    border-radius: 10px;
    padding: 14px 18px;
    border-left: 5px solid #4A90D9;
}
@media (max-width: 768px) {
    [data-testid="stMetric"] { padding: 10px 12px; }
    [data-testid="stMetricValue"] { font-size: 1rem !important; }
    [data-testid="stMetricLabel"] { font-size: 0.75rem !important; }
}
.stDownloadButton > button {
    background-color: #28a745 !important;
    color: white !important; border: none !important;
}
.stDownloadButton > button:hover {
    background-color: #218838 !important;
}
</style>
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TICKER UNIVERSE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
US_BOND = {
    "SGOV": "iShares 0-3M Treasury Bond",
    "SHY":  "iShares 1-3Y Treasury Bond",
    "IEI":  "iShares 3-7Y Treasury Bond",
    "IEF":  "iShares 7-10Y Treasury Bond",
    "TLT":  "iShares 20+Y Treasury Bond",
}
KR_BOND = {
    "114260.KS": "KODEX 국고채3년",
    "471230.KS": "KODEX 국고채10년액티브",
    "439870.KS": "KODEX 국고채30년액티브",
}
SP500_EQ = {
    "SPY":       "SPDR S&P 500 Trust",
    "VOO":       "Vanguard S&P 500",
    "360750.KS": "TIGER 미국S&P500",
}
NASDAQ_EQ = {
    "QQQ":       "Invesco QQQ Trust",
    "QQQM":      "Invesco NASDAQ 100",
    "133690.KS": "TIGER 미국나스닥100",
}
CASH_OPTS = {
    "153130.KS":    "KODEX 단기채권",
    "BANK_DEPOSIT": "은대 (고정 연 2.53%)",
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AUTHENTICATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def show_login():
    """로그인 폼 표시. st.secrets 우선, fallback: admin/infinity2026."""
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("## 🔐 로그인")
        st.caption("국채·ETF 혼합형 펀드 백테스팅 시스템")
        with st.form("login_form"):
            user = st.text_input("사용자명")
            pw = st.text_input("비밀번호", type="password")
            submitted = st.form_submit_button("로그인", use_container_width=True)
            if submitted:
                try:
                    valid_u = st.secrets["credentials"]["username"]
                    valid_p = st.secrets["credentials"]["password"]
                except Exception:
                    valid_u, valid_p = "admin", "infinity2026"
                if user == valid_u and pw == valid_p:
                    st.session_state["authenticated"] = True
                    st.session_state["username"] = user
                    st.rerun()
                else:
                    st.error("❌ 사용자명 또는 비밀번호가 올바르지 않습니다.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DATA FETCHING  (st.cache_data — TTL 1시간)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@st.cache_data(ttl=3600, show_spinner="📡 시세 데이터 로딩 중...")
def fetch_prices(tickers: tuple, start: str, end: str) -> pd.DataFrame:
    """yfinance 에서 종가(Adjusted Close) 일봉 다운로드."""
    if not tickers:
        return pd.DataFrame()
    all_data: dict[str, pd.Series] = {}
    for ticker in tickers:
        try:
            df = yf.download(
                ticker, start=start, end=end,
                auto_adjust=True, progress=False,
            )
            if df.empty:
                continue
            col = df["Close"].squeeze()
            if isinstance(col, pd.DataFrame):
                col = col.iloc[:, 0]
            all_data[ticker] = col
        except Exception:
            continue
    if not all_data:
        return pd.DataFrame()
    result = pd.DataFrame(all_data)
    # timezone 제거
    if result.index.tz is not None:
        result.index = result.index.tz_localize(None)
    return result.astype("float32")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FINANCIAL METRICS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def calc_cagr(nav: pd.Series) -> float:
    """Compound Annual Growth Rate (%)."""
    n_years = (nav.index[-1] - nav.index[0]).days / 365.25
    if n_years <= 0 or nav.iloc[0] <= 0:
        return 0.0
    return (float(nav.iloc[-1] / nav.iloc[0]) ** (1 / n_years) - 1) * 100


def calc_mdd(nav: pd.Series) -> float:
    """Maximum Drawdown (%, 음수)."""
    peak = nav.cummax()
    dd = (nav - peak) / peak
    return float(dd.min()) * 100


def calc_volatility(returns: pd.Series) -> float:
    """연환산 변동성 (%)."""
    return float(returns.std() * np.sqrt(252) * 100)


def calc_sharpe(returns: pd.Series, rf_annual: float = 0.03) -> float:
    """샤프 지수 (연환산)."""
    rf_daily = (1 + rf_annual) ** (1 / 252) - 1
    excess = returns - rf_daily
    std = excess.std()
    if std == 0 or np.isnan(std):
        return 0.0
    return float((excess.mean() / std) * np.sqrt(252))


def calc_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI 계산."""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_drawdown_series(nav: pd.Series) -> pd.Series:
    """일별 누적 낙폭 (%)."""
    peak = nav.cummax()
    return ((nav - peak) / peak) * 100


def calc_yearly_returns(nav: pd.Series) -> pd.Series:
    """연도별 수익률 (%)."""
    yearly: dict[int, float] = {}
    for yr in sorted(nav.index.year.unique()):
        yr_data = nav[nav.index.year == yr]
        if yr_data.empty:
            continue
        prev = nav[nav.index.year == yr - 1]
        start_val = float(prev.iloc[-1]) if len(prev) > 0 else float(yr_data.iloc[0])
        if start_val <= 0:
            continue
        yearly[yr] = (float(yr_data.iloc[-1]) / start_val - 1) * 100
    return pd.Series(yearly, dtype="float64", name="Return(%)")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  RSI TAA SIGNAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def compute_rsi_signal(
    rsi: pd.Series,
    entry_threshold: int = 30,
    exit_threshold: int = 60,
    max_days: int = 20,
) -> pd.Series:
    """RSI 과매도 진입/탈출 시그널 (1=진입, 0=미진입)."""
    signal = np.zeros(len(rsi), dtype="float32")
    in_pos = False
    held = 0
    for i in range(len(rsi)):
        val = rsi.iloc[i]
        if np.isnan(val):
            continue
        if not in_pos:
            if val < entry_threshold:
                in_pos = True
                held = 0
                signal[i] = 1
        else:
            held += 1
            if val > exit_threshold or held > max_days:
                in_pos = False
            else:
                signal[i] = 1
    return pd.Series(signal, index=rsi.index)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  WEIGHT CALCULATOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _calc_weights(params: dict, available: list[str]) -> dict[str, float]:
    """파라미터 기반 자산배분 비중 산출 (합계 = 1.0)."""
    weights: dict[str, float] = {}

    equity_pct = params["equity_pct"] / 100
    alt_cash_pct = params["alt_cash_pct"] / 100
    bond_pct = max(0.0, 1.0 - equity_pct - alt_cash_pct)

    # ── 주식 ──
    us_eq = [t for t in params["us_equity"] if t in available]
    kr_eq = [t for t in params["kr_equity"] if t in available]
    if us_eq or kr_eq:
        if us_eq and kr_eq:
            us_r = params.get("us_equity_ratio", 50) / 100
        elif us_eq:
            us_r = 1.0
        else:
            us_r = 0.0
        us_total = equity_pct * us_r
        kr_total = equity_pct * (1 - us_r)
        for t in us_eq:
            weights[t] = us_total / len(us_eq)
        for t in kr_eq:
            weights[t] = kr_total / len(kr_eq)
    else:
        bond_pct += equity_pct          # 주식 미선택 → 채권에 합산

    # ── 대체(Gold) + 현금 ──
    gold_on = params["gold_enabled"] and "GLDM" in available
    cash_tk = params["cash_ticker"]
    cash_ok = cash_tk and (cash_tk in available or cash_tk == "BANK_DEPOSIT")

    if gold_on and cash_ok:
        g_r = params.get("gold_cash_ratio", 50) / 100
        weights["GLDM"] = alt_cash_pct * g_r
        weights[cash_tk] = alt_cash_pct * (1 - g_r)
    elif gold_on:
        weights["GLDM"] = alt_cash_pct
    elif cash_ok:
        weights[cash_tk] = alt_cash_pct
    else:
        bond_pct += alt_cash_pct        # 둘 다 없으면 채권에 합산

    # ── 채권 ──
    us_bd = [t for t in params["us_bonds"] if t in available]
    kr_bd = [t for t in params["kr_bonds"] if t in available]
    if us_bd or kr_bd:
        if us_bd and kr_bd:
            ub_r = params.get("us_bond_ratio", 50) / 100
        elif us_bd:
            ub_r = 1.0
        else:
            ub_r = 0.0
        us_b_total = bond_pct * ub_r
        kr_b_total = bond_pct * (1 - ub_r)
        for t in us_bd:
            weights[t] = us_b_total / len(us_bd)
        for t in kr_bd:
            weights[t] = kr_b_total / len(kr_bd)

    # 정규화
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}
    return weights


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BACKTESTING ENGINE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def run_backtest(params: dict) -> dict | None:
    """
    전체 백테스팅 파이프라인:
      1) 데이터 수집  2) 환율 처리  3) TAA 시그널
      4) 포트폴리오 수익률  5) 메트릭 산출
    """
    # ── 1. 포트폴리오 티커 집계 ──
    portfolio_tickers: list[str] = []
    us_tickers: list[str] = []  # USD 표시 → FX 변환 필요
    kr_tickers: list[str] = []  # KRW 표시

    for t in params["us_bonds"]:
        portfolio_tickers.append(t); us_tickers.append(t)
    for t in params["kr_bonds"]:
        portfolio_tickers.append(t); kr_tickers.append(t)
    for t in params["us_equity"]:
        portfolio_tickers.append(t); us_tickers.append(t)
    for t in params["kr_equity"]:
        portfolio_tickers.append(t); kr_tickers.append(t)
    if params["gold_enabled"]:
        portfolio_tickers.append("GLDM"); us_tickers.append("GLDM")
    cash_tk = params["cash_ticker"]
    if cash_tk and cash_tk != "BANK_DEPOSIT":
        portfolio_tickers.append(cash_tk); kr_tickers.append(cash_tk)

    # 벤치마크(SPY) + 환율은 항상 필요
    fetch_list = list(set(portfolio_tickers + ["SPY", "KRW=X"]))

    # ── 2. 데이터 가져오기 ──
    prices = fetch_prices(
        tuple(sorted(fetch_list)),
        str(params["start_date"]),
        str(params["end_date"]),
    )
    if prices.empty:
        st.error("❌ 시세 데이터를 불러올 수 없습니다. 날짜·종목을 확인하세요.")
        return None

    # 누락 종목 경고
    available_pt = [t for t in portfolio_tickers if t in prices.columns]
    missing = [t for t in portfolio_tickers if t not in prices.columns]
    if missing:
        st.warning(f"⚠️ 다음 종목 데이터 없음(제외): {', '.join(missing)}")
    if not available_pt:
        st.error("❌ 유효한 포트폴리오 종목이 없습니다.")
        return None
    portfolio_tickers = available_pt
    us_tickers = [t for t in us_tickers if t in available_pt]
    kr_tickers = [t for t in kr_tickers if t in available_pt]

    # ── 3. 환율 ──
    has_fx = "KRW=X" in prices.columns and not prices["KRW=X"].isna().all()
    if has_fx:
        fx_raw = prices["KRW=X"].copy()
    # 포트폴리오 + 벤치마크 가격만 추출
    cols_needed = list(set(portfolio_tickers + (["SPY"] if "SPY" in prices.columns else [])))
    asset_prices = prices[cols_needed].copy()

    # ── 4. 은대(BANK_DEPOSIT) 합성 데이터 ──
    if cash_tk == "BANK_DEPOSIT":
        n = len(asset_prices)
        daily_rate = (1 + 0.0253) ** (1 / 252) - 1
        bank_nav = 100.0 * (1 + daily_rate) ** np.arange(n)
        asset_prices["BANK_DEPOSIT"] = bank_nav.astype("float32")
        portfolio_tickers.append("BANK_DEPOSIT")
        kr_tickers.append("BANK_DEPOSIT")

    # ── 5. 공통 날짜 정렬 ──
    asset_prices = asset_prices.ffill(limit=5)
    first_valid = asset_prices.apply(lambda s: s.first_valid_index()).max()
    last_valid  = asset_prices.apply(lambda s: s.last_valid_index()).min()
    if first_valid is None or last_valid is None or first_valid >= last_valid:
        st.error("❌ 공통 데이터 구간이 충분하지 않습니다.")
        return None
    asset_prices = asset_prices.loc[first_valid:last_valid].dropna()

    if has_fx:
        fx_raw = fx_raw.reindex(asset_prices.index).ffill().bfill()
        fx_returns = fx_raw.pct_change().fillna(0)
    else:
        fx_returns = pd.Series(0.0, index=asset_prices.index, dtype="float32")
        st.info("ℹ️ USD/KRW 환율 데이터 미수신 — 환율 변동 미반영")

    # 상장일 조정 안내
    user_start = pd.Timestamp(params["start_date"])
    if first_valid > user_start:
        st.info(
            f"ℹ️ 일부 ETF 상장일 제한으로 실제 분석 구간: "
            f"**{first_valid.strftime('%Y-%m-%d')}** ~ "
            f"**{last_valid.strftime('%Y-%m-%d')}**"
        )

    # ── 6. 일별 수익률 ──
    returns = asset_prices.pct_change().iloc[1:]
    fx_ret = fx_returns.reindex(returns.index).fillna(0)

    hedge_ratio = params["hedge_ratio"] / 100  # 0 = 환오픈, 1 = 완전 헤지

    # 환오픈 수익률 (원화 환산)
    ret_open = returns.copy()
    for t in us_tickers:
        if t in ret_open.columns:
            ret_open[t] = (1 + returns[t]) * (1 + fx_ret * (1 - hedge_ratio)) - 1

    # 환헤지(100%) 수익률 — 비교용
    ret_hedged = returns.copy()  # USD 수익률 그대로 (FX 미반영)

    # 벤치마크: SPY 원화 수익률 (환오픈)
    if "SPY" in returns.columns:
        bench_open = (1 + returns["SPY"]) * (1 + fx_ret) - 1
    else:
        bench_open = pd.Series(0.0, index=returns.index)

    # ── 7. 비중 산출 ──
    weights = _calc_weights(params, portfolio_tickers)
    if not weights:
        st.error("❌ 유효 비중이 없습니다. 종목을 확인하세요.")
        return None

    weight_vec = np.array([weights.get(t, 0.0) for t in portfolio_tickers], dtype="float64")

    # ── 8. TAA 시그널 ──
    taa_signal = pd.Series(0.0, index=returns.index)

    if params["rsi_taa_enabled"] and "SPY" in asset_prices.columns:
        spy_rsi = calc_rsi(asset_prices["SPY"], params["rsi_period"])
        spy_rsi = spy_rsi.reindex(returns.index)
        taa_signal = compute_rsi_signal(
            spy_rsi,
            params["rsi_entry"],
            params["rsi_exit"],
            params["rsi_max_days"],
        )

    if params["turnaround_enabled"] and params["turnaround_years"]:
        t_mask = returns.index.year.isin(params["turnaround_years"])
        taa_signal = ((taa_signal > 0) | t_mask).astype("float32")

    # ── 9. TAA 적용 비중 행렬 ──
    n_days = len(returns)
    weight_matrix = np.tile(weight_vec, (n_days, 1))  # (days, assets)

    equity_all = [t for t in params["us_equity"] + params["kr_equity"] if t in portfolio_tickers]
    bond_all   = [t for t in params["us_bonds"]  + params["kr_bonds"]  if t in portfolio_tickers]

    eq_idx = [i for i, t in enumerate(portfolio_tickers) if t in equity_all]
    bd_idx = [i for i, t in enumerate(portfolio_tickers) if t in bond_all]

    base_eq_w  = weight_vec[eq_idx].sum() if eq_idx else 0.0
    base_bd_w  = weight_vec[bd_idx].sum() if bd_idx else 0.0
    target_eq  = 0.30  # TAA 시 최대 주식 비중

    taa_mask = taa_signal.values > 0
    if taa_mask.any() and base_eq_w > 0 and base_bd_w > 0 and target_eq > base_eq_w:
        eq_scale = target_eq / base_eq_w
        reduce   = target_eq - base_eq_w
        bd_scale = max(0.0, (base_bd_w - reduce) / base_bd_w)
        for i in eq_idx:
            weight_matrix[taa_mask, i] = weight_vec[i] * eq_scale
        for i in bd_idx:
            weight_matrix[taa_mask, i] = weight_vec[i] * bd_scale

    # ── 10. 포트폴리오 수익률 ──
    ret_open_mat   = ret_open[portfolio_tickers].values
    ret_hedged_mat = ret_hedged[portfolio_tickers].values

    port_open   = (ret_open_mat   * weight_matrix).sum(axis=1)
    port_hedged = (ret_hedged_mat * weight_matrix).sum(axis=1)

    # 공모주 Alpha 가산
    alpha_daily = params["ipo_alpha"] / 100 / 252
    port_open   += alpha_daily
    port_hedged += alpha_daily

    port_open   = pd.Series(port_open,   index=returns.index, dtype="float64")
    port_hedged = pd.Series(port_hedged, index=returns.index, dtype="float64")

    # ── 11. NAV 산출 ──
    nav_open    = (1 + port_open).cumprod()   * 100
    nav_hedged  = (1 + port_hedged).cumprod() * 100
    nav_bench   = (1 + bench_open).cumprod()  * 100

    # ── 12. 메트릭 ──
    cagr_val  = calc_cagr(nav_open)
    mdd_val   = calc_mdd(nav_open)
    vol_val   = calc_volatility(port_open)
    sharpe_val = calc_sharpe(port_open, rf_annual=0.03)

    cagr_hedged = calc_cagr(nav_hedged)
    fx_contrib  = cagr_val - cagr_hedged

    cumul   = (float(nav_open.iloc[-1])  / float(nav_open.iloc[0])  - 1) * 100
    b_cumul = (float(nav_bench.iloc[-1]) / float(nav_bench.iloc[0]) - 1) * 100

    # ── 13. 결과 패키징 ──
    return {
        "nav_open":     nav_open,
        "nav_hedged":   nav_hedged,
        "nav_benchmark": nav_bench,
        "daily_returns": port_open,
        "cagr":         cagr_val,
        "mdd":          mdd_val,
        "volatility":   vol_val,
        "sharpe":       sharpe_val,
        "fx_contribution": fx_contrib,
        "cumulative_return":     cumul,
        "benchmark_cumulative":  b_cumul,
        "yearly_portfolio": calc_yearly_returns(nav_open),
        "yearly_benchmark": calc_yearly_returns(nav_bench),
        "yearly_hedged":    calc_yearly_returns(nav_hedged),
        "drawdown":         calc_drawdown_series(nav_open),
        "weights":          weights,
        "analysis_start":   returns.index[0],
        "analysis_end":     returns.index[-1],
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SIDEBAR UI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def render_sidebar() -> tuple[dict, bool]:
    """사이드바 파라미터 위젯을 렌더링하고 dict 로 반환."""
    with st.sidebar:
        # ── 로그아웃 ──
        c1, c2 = st.columns([3, 1])
        with c1:
            st.markdown(f"👤 **{st.session_state.get('username', '')}**")
        with c2:
            if st.button("로그아웃", key="btn_logout"):
                for k in list(st.session_state.keys()):
                    del st.session_state[k]
                st.rerun()
        st.divider()
        st.header("⚙️ 파라미터 설정")

        # ── 분석 기간 ──
        with st.expander("📅 분석 기간", expanded=True):
            start_date = st.date_input("시작일", value=date(2015, 1, 1))
            end_date   = st.date_input("종료일", value=date.today())

        # ── 채권 ETF ──
        with st.expander("🏛️ 채권 ETF 유니버스", expanded=True):
            st.caption("**미국 국채 ETF**")
            us_bonds = st.multiselect(
                "미국 국채", list(US_BOND.keys()), default=["IEF", "TLT"],
                format_func=lambda x: f"{x}  ({US_BOND[x]})",
                label_visibility="collapsed",
            )
            st.caption("**한국 국고채 ETF**")
            kr_bonds = st.multiselect(
                "한국 국고채", list(KR_BOND.keys()), default=["471230.KS"],
                format_func=lambda x: f"{x.replace('.KS','')}  ({KR_BOND[x]})",
                label_visibility="collapsed",
            )

        # ── 주가지수 ETF ──
        with st.expander("📈 주가지수 ETF 유니버스", expanded=False):
            st.caption("**S&P500 계열**")
            sp_sel = st.multiselect(
                "S&P500", list(SP500_EQ.keys()), default=["SPY"],
                format_func=lambda x: f"{x.replace('.KS','')}  ({SP500_EQ[x]})",
                label_visibility="collapsed",
            )
            st.caption("**NASDAQ100 계열**")
            nq_sel = st.multiselect(
                "NASDAQ100", list(NASDAQ_EQ.keys()), default=[],
                format_func=lambda x: f"{x.replace('.KS','')}  ({NASDAQ_EQ[x]})",
                label_visibility="collapsed",
            )
        all_eq = sp_sel + nq_sel
        us_equity = [t for t in all_eq if not t.endswith(".KS")]
        kr_equity = [t for t in all_eq if t.endswith(".KS")]

        # ── 대체 · 현금성 ──
        with st.expander("🏆 대체·현금성 자산", expanded=False):
            gold_on = st.toggle("Gold (GLDM) 편입", value=False)
            cash_ticker = st.selectbox(
                "현금성 자산", list(CASH_OPTS.keys()),
                format_func=lambda x: (
                    f"{x.replace('.KS','')} - {CASH_OPTS[x]}"
                    if x != "BANK_DEPOSIT" else CASH_OPTS[x]
                ),
            )

        # ── 자산배분 비중 ──
        with st.expander("⚖️ 자산배분 비중", expanded=True):
            equity_pct = st.slider(
                "주가지수 ETF 합산 (%)", 0, 30, 10, 1,
                help="미국+한국 합산 최대 30%",
            )
            us_equity_ratio = 100
            if us_equity and kr_equity:
                us_equity_ratio = st.slider(
                    "주식 내 미국 비율 (%)", 0, 100, 50, 5,
                )

            alt_cash_pct = st.slider(
                "대체+현금성 자산 (%)", 0, 20, 0, 1,
                help="GLDM + 단기채/은대 합산, 채권에서 차감",
            )
            gold_cash_ratio = 50
            if gold_on and cash_ticker:
                gold_cash_ratio = st.slider("Gold / 현금 비율 (Gold %)", 0, 100, 50, 5)

            bond_pct = 100 - equity_pct - alt_cash_pct
            st.metric("채권 자동 배분", f"{bond_pct}%")

            us_bond_ratio = 50
            if us_bonds and kr_bonds:
                us_bond_ratio = st.slider("채권 내 미국 비율 (%)", 0, 100, 50, 5)

        # ── 공모주 Alpha ──
        with st.expander("💰 공모주 Alpha 가산", expanded=False):
            ipo_alpha = st.slider("연간 Alpha (%p)", 0.0, 1.0, 0.0, 0.05)

        # ── TAA ──
        with st.expander("🔄 동적 TAA 전략", expanded=False):
            st.caption("**[전략 1] RSI 과매도 탄력 운용**")
            rsi_on = st.toggle("RSI TAA 활성화", value=False)
            rsi_period = 14; rsi_entry = 30; rsi_exit = 60; rsi_max = 20
            if rsi_on:
                rsi_period = int(st.number_input("RSI 기간", 5, 30, 14, key="rsi_p"))
                rsi_entry  = int(st.number_input("과매도 진입 RSI", 10, 45, 30, key="rsi_e"))
                rsi_exit   = int(st.number_input("탈출 RSI", 50, 80, 60, key="rsi_x"))
                rsi_max    = int(st.number_input("최대 유지 영업일", 5, 60, 20, key="rsi_m"))

            st.caption("**[전략 2] 영업이익 턴어라운드 적극 투자**")
            ta_on = st.toggle("턴어라운드 모드 활성화", value=False)
            ta_years: list[int] = []
            if ta_on:
                yr_range = list(range(2015, date.today().year + 1))
                ta_years = st.multiselect("적극 투자 연도 선택", yr_range, default=[])

        # ── 환율 ──
        with st.expander("💱 환율·통화", expanded=False):
            hedge_ratio = st.slider(
                "환헤지 비중 (%)", 0, 100, 0, 5,
                help="0% = 환오픈(기본), 100% = 완전 헤지",
            )
            show_hedged = st.checkbox("환헤지 수익률 비교 라인 표시", value=False)

        st.divider()
        run_clicked = st.button(
            "🚀 시뮬레이션 재실행", type="primary", use_container_width=True,
        )

    params = {
        "start_date":       start_date,
        "end_date":         end_date,
        "us_bonds":         us_bonds,
        "kr_bonds":         kr_bonds,
        "us_equity":        us_equity,
        "kr_equity":        kr_equity,
        "gold_enabled":     gold_on,
        "cash_ticker":      cash_ticker,
        "equity_pct":       equity_pct,
        "us_equity_ratio":  us_equity_ratio,
        "alt_cash_pct":     alt_cash_pct,
        "gold_cash_ratio":  gold_cash_ratio,
        "us_bond_ratio":    us_bond_ratio,
        "ipo_alpha":        ipo_alpha,
        "rsi_taa_enabled":  rsi_on,
        "rsi_period":       rsi_period,
        "rsi_entry":        rsi_entry,
        "rsi_exit":         rsi_exit,
        "rsi_max_days":     rsi_max,
        "turnaround_enabled": ta_on,
        "turnaround_years": ta_years,
        "hedge_ratio":      hedge_ratio,
        "show_hedged_line": show_hedged,
    }
    return params, run_clicked


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DASHBOARD RENDER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def render_dashboard(res: dict, show_hedged: bool):
    """메인 대시보드: KPI · 차트 · 테이블 · 엑셀 다운로드."""
    st.title("📊 국채·ETF 혼합형 펀드 백테스팅 결과")
    period = (
        f"{res['analysis_start'].strftime('%Y-%m-%d')} ~ "
        f"{res['analysis_end'].strftime('%Y-%m-%d')}"
    )
    st.caption(f"분석 기간: {period}")

    # ── KPI 카드 5개 ──
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        delta_str = f"목표 8% 대비 {res['cagr'] - 8:+.2f}%p"
        st.metric("연평균 수익률 (CAGR)", f"{res['cagr']:.2f}%", delta=delta_str)
    with c2:
        st.metric("최대 낙폭 (MDD)", f"{res['mdd']:.2f}%")
    with c3:
        st.metric(
            "변동성 / 샤프",
            f"{res['volatility']:.2f}%",
            delta=f"Sharpe {res['sharpe']:.2f}",
            delta_color="off",
        )
    with c4:
        fx_sign = "+" if res["fx_contribution"] >= 0 else ""
        st.metric("연평균 환차익 기여도", f"{fx_sign}{res['fx_contribution']:.2f}%p")
    with c5:
        st.metric(
            "누적 수익률",
            f"{res['cumulative_return']:.1f}%",
            delta=f"벤치마크 {res['benchmark_cumulative']:.1f}%",
            delta_color="off",
        )

    st.divider()

    # ── Chart 1 : 누적 NAV ──
    st.subheader("📈 Chart 1 — 누적 자산가치(NAV) 추이")
    fig_nav = go.Figure()
    fig_nav.add_trace(go.Scatter(
        x=res["nav_open"].index, y=res["nav_open"].values,
        name="포트폴리오 (환오픈)",
        line=dict(color="#2962FF", width=2.2),
    ))
    if show_hedged:
        fig_nav.add_trace(go.Scatter(
            x=res["nav_hedged"].index, y=res["nav_hedged"].values,
            name="포트폴리오 (환헤지)",
            line=dict(color="#FF6D00", width=2, dash="dash"),
        ))
    fig_nav.add_trace(go.Scatter(
        x=res["nav_benchmark"].index, y=res["nav_benchmark"].values,
        name="S&P500 벤치마크 (KRW)",
        line=dict(color="#00C853", width=1.5, dash="dot"),
    ))
    fig_nav.update_layout(
        template="plotly_white",
        hovermode="x unified",
        yaxis_title="NAV (시작 = 100)",
        legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center"),
        margin=dict(l=0, r=0, t=30, b=0),
        height=460,
    )
    st.plotly_chart(fig_nav, use_container_width=True)

    # ── Chart 2 : Drawdown ──
    st.subheader("📉 Chart 2 — 낙폭 추이 (Underwater Plot)")
    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(
        x=res["drawdown"].index, y=res["drawdown"].values,
        fill="tozeroy", name="낙폭",
        line=dict(color="#FF1744", width=1),
        fillcolor="rgba(255,23,68,0.15)",
    ))
    fig_dd.update_layout(
        template="plotly_white",
        hovermode="x unified",
        yaxis_title="Drawdown (%)",
        margin=dict(l=0, r=0, t=10, b=0),
        height=300,
    )
    st.plotly_chart(fig_dd, use_container_width=True)

    st.divider()

    # ── 테이블 ──
    t1, t2 = st.columns(2)

    with t1:
        st.subheader("📋 테이블 1 — 성과 · 리스크 요약")
        bench_ret = res["nav_benchmark"].pct_change().dropna()
        summary = pd.DataFrame({
            "지표": ["누적수익률", "CAGR", "연환산변동성", "샤프지수", "MDD"],
            "포트폴리오": [
                f"{res['cumulative_return']:.2f}%",
                f"{res['cagr']:.2f}%",
                f"{res['volatility']:.2f}%",
                f"{res['sharpe']:.2f}",
                f"{res['mdd']:.2f}%",
            ],
            "S&P500(KRW)": [
                f"{res['benchmark_cumulative']:.2f}%",
                f"{calc_cagr(res['nav_benchmark']):.2f}%",
                f"{calc_volatility(bench_ret):.2f}%",
                f"{calc_sharpe(bench_ret):.2f}",
                f"{calc_mdd(res['nav_benchmark']):.2f}%",
            ],
        })
        st.dataframe(summary, hide_index=True, use_container_width=True)

    with t2:
        st.subheader("📅 테이블 2 — 연도별 수익률 (%)")
        yearly = pd.DataFrame({
            "포트폴리오": res["yearly_portfolio"].round(2),
            "S&P500(KRW)": res["yearly_benchmark"].round(2),
        })
        if show_hedged:
            yearly["환헤지"] = res["yearly_hedged"].round(2)
        yearly.index.name = "연도"
        st.dataframe(yearly, use_container_width=True)

    st.divider()

    # ── 비중 정보 ──
    with st.expander("🔍 적용 자산 비중 상세", expanded=False):
        w_df = pd.DataFrame(
            [{"종목": k, "비중(%)": round(v * 100, 2)} for k, v in res["weights"].items()]
        ).sort_values("비중(%)", ascending=False).reset_index(drop=True)
        st.dataframe(w_df, hide_index=True, use_container_width=True)

    # ── 엑셀 다운로드 ──
    nav_df = pd.DataFrame({
        "Date":        res["nav_open"].index,
        "NAV_환오픈":   res["nav_open"].values.round(4),
        "NAV_환헤지":   res["nav_hedged"].values.round(4),
        "NAV_벤치마크": res["nav_benchmark"].values.round(4),
    })
    yearly_exp = pd.DataFrame({
        "연도":         res["yearly_portfolio"].index,
        "포트폴리오(%)": res["yearly_portfolio"].values.round(2),
        "벤치마크(%)":   res["yearly_benchmark"].values.round(2),
    })

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        summary.to_excel(w, sheet_name="성과요약", index=False)
        yearly_exp.to_excel(w, sheet_name="연도별수익률", index=False)
        nav_df.to_excel(w, sheet_name="일별NAV", index=False)

    st.download_button(
        label="📥 엑셀 다운로드  (국채_ETF_혼합형펀드_백테스팅_결과.xlsx)",
        data=buf.getvalue(),
        file_name="국채_ETF_혼합형펀드_백테스팅_결과.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def main():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    # ── 인증 ──
    if not st.session_state.get("authenticated"):
        show_login()
        return

    # ── 사이드바 ──
    params, run_clicked = render_sidebar()

    # ── 시뮬레이션 실행 ──
    if run_clicked:
        has_any = (
            params["us_bonds"] or params["kr_bonds"]
            or params["us_equity"] or params["kr_equity"]
            or params["gold_enabled"]
            or (params["cash_ticker"] and params["alt_cash_pct"] > 0)
        )
        if not has_any:
            st.error("❌ 최소 하나의 ETF를 선택하세요.")
            return

        with st.spinner("📊 시뮬레이션 실행 중… 잠시만 기다려 주세요."):
            results = run_backtest(params)

        if results is not None:
            st.session_state["results"] = results
            st.session_state["show_hedged"] = params["show_hedged_line"]

    # ── 결과 표시 ──
    if "results" in st.session_state:
        render_dashboard(
            st.session_state["results"],
            st.session_state.get("show_hedged", False),
        )
    else:
        st.markdown("## 📊 국채·ETF 혼합형 펀드 백테스팅 대시보드")
        st.info("👈 사이드바에서 파라미터를 설정한 후 **🚀 시뮬레이션 재실행** 버튼을 클릭하세요.")
        st.markdown(
            """
            ### 🏗️ 기본 구성
            | 자산군 | 기본 편입 | 비중 |
            |--------|----------|------|
            | 미국 국채 ETF | IEF (7-10Y), TLT (20+Y) | 약 45% 씩 |
            | 한국 국고채 ETF | 471230 (10년 액티브) | 잔여 |
            | 주가지수 ETF | SPY (S&P 500) | 10% |
            | 환율 | 환오픈 (USD 노출) | — |

            > 사이드바에서 종목·비중·전략을 자유롭게 변경하세요.
            """
        )


main()
