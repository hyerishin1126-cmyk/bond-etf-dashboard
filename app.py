"""
국채·지수 ETF 혼합형 펀드 백테스팅 대시보드
=====================================================
- 투자대상:
    1) 미국 국고채 ETF (SGOV, SHY, IEI, IEF, TLT, GOVT)
    2) 한국 국고채 ETF (KODEX 3년, KODEX 10년액티브, KODEX 30년액티브, KOSEF 10년, TIGER 10년)
    3) 미국 지수 ETF (SPY, VOO, IVV, QQQ, QQQM, DIA)
    4) 한국 지수 ETF (KODEX 200, TIGER 200, KODEX 코스닥150, KODEX 200TR, TIGER 미국S&P500, TIGER 미국나스닥100)
    5) 대체 및 현금성 자산 (Gold GLDM, KODEX 단기채권, 은대 2.53%)
- 기간 조회:
    - 2025년 1월 1일 이후 ~ 현재
    - 최근 1개월, 3개월, 6개월, YTD 등 짧은 기간(단기 모니터링) 즉시 조회 지원
    - 2015년~10년 장기 백테스팅 및 직접 사용자 지정 날짜 지원
- 투자비중:
    - 미국 국고채 0~100%
    - 한국 국고채 0~100%
    - 미국 지수 ETF 0~30%
    - 한국 지수 ETF 0~30%
    - 대체/현금성 0~20%
    - 공모주 Alpha 0~1%p
- 목표수익률 8%대 정밀 분석:
    - 국채 ETF 3~4%대 (90% × 4~5%)
    - 지수 ETF 0~3%대 (10% × 0~30%)
    - 환차익 3~5%대 (USD/KRW 환오픈 기대)
    - 공모주 0~1%대 (연 0~1%p 가산)
"""

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import date, timedelta
import io
import warnings

warnings.filterwarnings("ignore")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PAGE CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.set_page_config(
    page_title="국채·지수 ETF 혼합형 펀드 백테스팅",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CUSTOM CSS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CUSTOM_CSS = """
<style>
[data-testid="stMetric"] {
    background: #f8f9fa;
    border: 1px solid #dee2e6;
    border-radius: 10px;
    padding: 12px 16px;
    border-left: 5px solid #1E88E5;
}
@media (max-width: 768px) {
    [data-testid="stMetric"] { padding: 8px 10px; }
    [data-testid="stMetricValue"] { font-size: 1.05rem !important; }
    [data-testid="stMetricLabel"] { font-size: 0.75rem !important; }
}
.stDownloadButton > button {
    background-color: #2E7D32 !important;
    color: white !important;
    border: none !important;
    font-weight: 600 !important;
}
.stDownloadButton > button:hover {
    background-color: #1B5E20 !important;
}
.short-banner {
    background: #e8f5e9;
    border: 1px solid #a5d6a7;
    border-radius: 8px;
    padding: 10px 14px;
    margin-bottom: 15px;
    font-size: 0.92rem;
    color: #1b5e20;
}
</style>
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TICKER UNIVERSE (국내외 국채 & 국내외 지수 ETF)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
US_BOND = {
    "SGOV": "iShares 0-3M Treasury Bond (초단기)",
    "SHY":  "iShares 1-3Y Treasury Bond (단기 1-3년)",
    "IEI":  "iShares 3-7Y Treasury Bond (중기 3-7년)",
    "IEF":  "iShares 7-10Y Treasury Bond (중장기 7-10년)",
    "TLT":  "iShares 20+Y Treasury Bond (초장기 20년+)",
    "GOVT": "iShares U.S. Treasury Bond ETF (국채종합)",
}

KR_BOND = {
    "114260.KS": "KODEX 국고채3년",
    "471230.KS": "KODEX 국고채10년액티브",
    "439870.KS": "KODEX 국고채30년액티브",
    "148070.KS": "KOSEF 국고채10년",
    "305080.KS": "TIGER 국고채10년",
}

US_EQUITY = {
    "SPY":  "SPDR S&P 500 Trust (대표 S&P 500)",
    "VOO":  "Vanguard S&P 500 ETF",
    "IVV":  "iShares Core S&P 500 ETF",
    "QQQ":  "Invesco QQQ Trust (NASDAQ 100)",
    "QQQM": "Invesco NASDAQ 100 ETF",
    "DIA":  "SPDR Dow Jones Industrial Average",
}

KR_EQUITY = {
    "069500.KS": "KODEX 200 (한국 코스피200 대표)",
    "102110.KS": "TIGER 200 (코스피200)",
    "229200.KS": "KODEX 코스닥150 (코스닥 대표)",
    "305720.KS": "KODEX 200TR (배당재투자형)",
    "360750.KS": "TIGER 미국S&P500 (국내상장 환노출)",
    "133690.KS": "TIGER 미국나스닥100 (국내상장 환노출)",
    "379800.KS": "KODEX 미국S&P500TR (국내상장)",
}

CASH_OPTS = {
    "153130.KS":    "KODEX 단기채권",
    "BANK_DEPOSIT": "은대 (고정 연 2.53% 일할)",
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AUTHENTICATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def show_login():
    """로그인 폼 표시. st.secrets 우선, fallback: admin/infinity2026."""
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("## 🔐 로그인")
        st.caption("국채·지수 ETF 혼합형 펀드 퀀트 백테스팅 시스템")
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
#  DATA FETCHING (캐싱 1시간)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@st.cache_data(ttl=3600, show_spinner="📡 실시간 금융 데이터 로딩 중...")
def fetch_prices(tickers: tuple, start: str, end: str) -> pd.DataFrame:
    """yfinance Adjusted Close 일봉 다운로드."""
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
    if result.index.tz is not None:
        result.index = result.index.tz_localize(None)
    return result.astype("float32")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FINANCIAL METRICS (장기 및 단기 구간 정밀 산출)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def calc_returns_and_cagr(nav: pd.Series) -> tuple[float, float, bool]:
    """
    반환값: (표시수익률, 연환산수익률, 1년미만단기여부)
    - 1년 미만: 기간 단순 수익률(%)을 기본으로 하고, 연환산치를 함께 계산
    - 1년 이상: CAGR(연평균 복리 수익률 %)
    """
    if len(nav) < 2:
        return 0.0, 0.0, False
    days = (nav.index[-1] - nav.index[0]).days
    if days <= 0 or nav.iloc[0] <= 0:
        return 0.0, 0.0, False

    cum_ret = (float(nav.iloc[-1] / nav.iloc[0]) - 1) * 100
    n_years = days / 365.25
    is_short = n_years < 1.0

    if is_short:
        if days >= 14:
            annualized = ((1 + cum_ret / 100.0) ** (365.25 / days) - 1) * 100
        else:
            annualized = cum_ret
        return cum_ret, annualized, True
    else:
        cagr = ((float(nav.iloc[-1] / nav.iloc[0])) ** (1 / n_years) - 1) * 100
        return cagr, cagr, False

def calc_mdd(nav: pd.Series) -> float:
    """Maximum Drawdown (%, 음수)."""
    peak = nav.cummax()
    dd = (nav - peak) / peak
    return float(dd.min()) * 100

def calc_volatility(returns: pd.Series) -> float:
    """연환산 변동성 (%)."""
    if len(returns) < 2:
        return 0.0
    return float(returns.std() * np.sqrt(252) * 100)

def calc_sharpe(returns: pd.Series, rf_annual: float = 0.03) -> float:
    """샤프 지수 (연환산, 무위험 3.0% 가정)."""
    if len(returns) < 2:
        return 0.0
    rf_daily = (1 + rf_annual) ** (1 / 252) - 1
    excess = returns - rf_daily
    std = excess.std()
    if std == 0 or np.isnan(std):
        return 0.0
    return float((excess.mean() / std) * np.sqrt(252))

def calc_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI 계산 (데이터 부족 시 결측값 안전 처리)."""
    if len(prices) <= period:
        return pd.Series(np.nan, index=prices.index)
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calc_drawdown_series(nav: pd.Series) -> pd.Series:
    """일별 낙폭 (%)."""
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
#  WEIGHT ALLOCATION LOGIC
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _calc_weights(params: dict, available: list[str]) -> tuple[dict[str, float], dict[str, float]]:
    w_us_bond = params["weight_us_bond"] / 100.0
    w_kr_bond = params["weight_kr_bond"] / 100.0
    w_us_eq   = params["weight_us_eq"] / 100.0
    w_kr_eq   = params["weight_kr_eq"] / 100.0
    w_alt     = params["weight_alt_cash"] / 100.0

    sum_raw = w_us_bond + w_kr_bond + w_us_eq + w_kr_eq + w_alt
    if sum_raw <= 0:
        return {}, {}

    scale = 1.0 / sum_raw
    c_us_bond = w_us_bond * scale
    c_kr_bond = w_kr_bond * scale
    c_us_eq   = w_us_eq * scale
    c_kr_eq   = w_kr_eq * scale
    c_alt     = w_alt * scale

    weights: dict[str, float] = {}

    us_bd_list = [t for t in params["us_bonds"] if t in available]
    if us_bd_list and c_us_bond > 0:
        for t in us_bd_list:
            weights[t] = c_us_bond / len(us_bd_list)
    else:
        c_kr_bond += c_us_bond

    kr_bd_list = [t for t in params["kr_bonds"] if t in available]
    if kr_bd_list and c_kr_bond > 0:
        for t in kr_bd_list:
            weights[t] = weights.get(t, 0.0) + (c_kr_bond / len(kr_bd_list))

    us_eq_list = [t for t in params["us_equity"] if t in available]
    if us_eq_list and c_us_eq > 0:
        for t in us_eq_list:
            weights[t] = c_us_eq / len(us_eq_list)

    kr_eq_list = [t for t in params["kr_equity"] if t in available]
    if kr_eq_list and c_kr_eq > 0:
        for t in kr_eq_list:
            weights[t] = c_kr_eq / len(kr_eq_list)

    gold_on = params["gold_enabled"] and "GLDM" in available
    cash_tk = params["cash_ticker"]
    cash_ok = cash_tk and (cash_tk in available or cash_tk == "BANK_DEPOSIT")

    if c_alt > 0:
        if gold_on and cash_ok:
            weights["GLDM"] = c_alt * 0.5
            weights[cash_tk] = c_alt * 0.5
        elif gold_on:
            weights["GLDM"] = c_alt
        elif cash_ok:
            weights[cash_tk] = c_alt

    tot = sum(weights.values())
    if tot > 0:
        weights = {k: v / tot for k, v in weights.items()}

    category_summary = {
        "미국 국고채": c_us_bond,
        "한국 국고채": c_kr_bond,
        "미국 지수 ETF": c_us_eq,
        "한국 지수 ETF": c_kr_eq,
        "대체·현금성": c_alt,
    }
    return weights, category_summary

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BACKTEST ENGINE & ATTRIBUTION BREAKDOWN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def run_backtest(params: dict) -> dict | None:
    portfolio_tickers: list[str] = []
    us_tickers: list[str] = []
    kr_tickers: list[str] = []

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

    fetch_list = list(set(portfolio_tickers + ["SPY", "KRW=X"]))

    # 1. 시세 데이터 수집
    prices = fetch_prices(
        tuple(sorted(fetch_list)),
        str(params["start_date"]),
        str(params["end_date"]),
    )
    if prices.empty:
        st.error("❌ 시세 데이터를 불러올 수 없습니다. 날짜와 종목을 확인하세요.")
        return None

    available_pt = [t for t in portfolio_tickers if t in prices.columns]
    missing = [t for t in portfolio_tickers if t not in prices.columns]
    if missing:
        st.warning(f"⚠️ 다음 종목 데이터 부재로 제외: {', '.join(missing)}")
    if not available_pt:
        st.error("❌ 유효한 포트폴리오 종목이 존재하지 않습니다.")
        return None

    portfolio_tickers = available_pt
    us_tickers = [t for t in us_tickers if t in available_pt]
    kr_tickers = [t for t in kr_tickers if t in available_pt]

    # 2. 환율 데이터
    has_fx = "KRW=X" in prices.columns and not prices["KRW=X"].isna().all()
    fx_raw = prices["KRW=X"].copy() if has_fx else None

    # 3. 은대 합성 데이터 생성
    cols_needed = list(set(portfolio_tickers + (["SPY"] if "SPY" in prices.columns else [])))
    asset_prices = prices[cols_needed].copy()
    if cash_tk == "BANK_DEPOSIT":
        n = len(asset_prices)
        daily_rate = (1 + 0.0253) ** (1 / 252) - 1
        bank_nav = 100.0 * (1 + daily_rate) ** np.arange(n)
        asset_prices["BANK_DEPOSIT"] = bank_nav.astype("float32")
        portfolio_tickers.append("BANK_DEPOSIT")
        kr_tickers.append("BANK_DEPOSIT")

    # 4. 공통 데이터 구간 정렬
    asset_prices = asset_prices.ffill(limit=5)
    first_valid = asset_prices.apply(lambda s: s.first_valid_index()).max()
    last_valid  = asset_prices.apply(lambda s: s.last_valid_index()).min()
    if first_valid is None or last_valid is None or first_valid >= last_valid:
        st.error("❌ 선택한 기간의 거래일 데이터가 부족합니다 (최소 2일 이상 필요).")
        return None
    asset_prices = asset_prices.loc[first_valid:last_valid].dropna()

    if len(asset_prices) < 2:
        st.error("❌ 분석에 필요한 유효 거래일 데이터가 2일 미만입니다. 기간을 조금 더 넓혀주세요.")
        return None

    if has_fx:
        fx_raw = fx_raw.reindex(asset_prices.index).ffill().bfill()
        fx_returns = fx_raw.pct_change().fillna(0)
    else:
        fx_returns = pd.Series(0.0, index=asset_prices.index, dtype="float32")

    user_start = pd.Timestamp(params["start_date"])
    if first_valid > user_start:
        st.info(
            f"ℹ️ ETF 상장일 제한으로 실제 공통 백테스팅 구간: "
            f"**{first_valid.strftime('%Y-%m-%d')}** ~ **{last_valid.strftime('%Y-%m-%d')}**"
        )

    # 5. 일별 수익률 계산
    returns = asset_prices.pct_change().iloc[1:]
    if returns.empty:
        st.error("❌ 일별 수익률을 계산할 수 없습니다. 더 긴 기간을 선택하세요.")
        return None

    fx_ret = fx_returns.reindex(returns.index).fillna(0)
    hedge_ratio = params["hedge_ratio"] / 100.0

    # 환오픈 (원화 환산) 수익률
    ret_open = returns.copy()
    for t in us_tickers:
        if t in ret_open.columns:
            ret_open[t] = (1 + returns[t]) * (1 + fx_ret * (1 - hedge_ratio)) - 1

    # 완전 환헤지 수익률
    ret_hedged = returns.copy()

    # 벤치마크: SPY 원화 환산
    if "SPY" in returns.columns:
        bench_open = (1 + returns["SPY"]) * (1 + fx_ret) - 1
    else:
        bench_open = pd.Series(0.0, index=returns.index)

    # 6. 비중 산출
    weights, cat_weights = _calc_weights(params, portfolio_tickers)
    if not weights:
        st.error("❌ 유효 비중을 산출할 수 없습니다.")
        return None

    weight_vec = np.array([weights.get(t, 0.0) for t in portfolio_tickers], dtype="float64")

    # 7. TAA 시그널 (RSI 과매도 / 턴어라운드)
    taa_signal = pd.Series(0.0, index=returns.index)
    if params["rsi_taa_enabled"] and "SPY" in asset_prices.columns:
        spy_rsi = calc_rsi(asset_prices["SPY"], params["rsi_period"]).reindex(returns.index)
        taa_signal = compute_rsi_signal(
            spy_rsi, params["rsi_entry"], params["rsi_exit"], params["rsi_max_days"]
        )

    if params["turnaround_enabled"] and params["turnaround_years"]:
        t_mask = returns.index.year.isin(params["turnaround_years"])
        taa_signal = ((taa_signal > 0) | t_mask).astype("float32")

    # 8. TAA 동적 비중 반영
    n_days = len(returns)
    weight_matrix = np.tile(weight_vec, (n_days, 1))

    all_eq_tickers = [t for t in params["us_equity"] + params["kr_equity"] if t in portfolio_tickers]
    all_bd_tickers = [t for t in params["us_bonds"] + params["kr_bonds"] if t in portfolio_tickers]

    eq_idx = [i for i, t in enumerate(portfolio_tickers) if t in all_eq_tickers]
    bd_idx = [i for i, t in enumerate(portfolio_tickers) if t in all_bd_tickers]

    base_eq_w = weight_vec[eq_idx].sum() if eq_idx else 0.0
    base_bd_w = weight_vec[bd_idx].sum() if bd_idx else 0.0
    target_eq = 0.30

    taa_mask = taa_signal.values > 0
    if taa_mask.any() and base_eq_w > 0 and base_bd_w > 0 and target_eq > base_eq_w:
        eq_scale = target_eq / base_eq_w
        reduce   = target_eq - base_eq_w
        bd_scale = max(0.0, (base_bd_w - reduce) / base_bd_w)
        for i in eq_idx:
            weight_matrix[taa_mask, i] = weight_vec[i] * eq_scale
        for i in bd_idx:
            weight_matrix[taa_mask, i] = weight_vec[i] * bd_scale

    # 9. 포트폴리오 일별 수익률 산출
    ret_open_mat   = ret_open[portfolio_tickers].values
    ret_hedged_mat = ret_hedged[portfolio_tickers].values

    port_open   = (ret_open_mat   * weight_matrix).sum(axis=1)
    port_hedged = (ret_hedged_mat * weight_matrix).sum(axis=1)

    # 공모주 Alpha 가산
    alpha_daily = params["ipo_alpha"] / 100.0 / 252.0
    port_open   += alpha_daily
    port_hedged += alpha_daily

    port_open   = pd.Series(port_open,   index=returns.index, dtype="float64")
    port_hedged = pd.Series(port_hedged, index=returns.index, dtype="float64")

    # 10. NAV 산출
    nav_open    = (1 + port_open).cumprod()   * 100.0
    nav_hedged  = (1 + port_hedged).cumprod() * 100.0
    nav_bench   = (1 + bench_open).cumprod()  * 100.0

    # 11. 주요 KPI 산출 (단기/장기 구분)
    metric_open, ann_open, is_short = calc_returns_and_cagr(nav_open)
    metric_hedged, ann_hedged, _    = calc_returns_and_cagr(nav_hedged)
    mdd_val     = calc_mdd(nav_open)
    vol_val     = calc_volatility(port_open)
    sharpe_val  = calc_sharpe(port_open, rf_annual=0.03)
    fx_contrib  = ann_open - ann_hedged

    cumul   = (float(nav_open.iloc[-1])  / float(nav_open.iloc[0])  - 1) * 100
    b_cumul = (float(nav_bench.iloc[-1]) / float(nav_bench.iloc[0]) - 1) * 100

    # 12. 목표수익률 8%대 대비 성과 기여도 분해 (Attribution)
    bond_daily = np.zeros(n_days)
    for i in bd_idx:
        bond_daily += ret_hedged_mat[:, i] * weight_matrix[:, i]
    if n_days > 0:
        if is_short:
            cagr_bond = (float(np.prod(1 + bond_daily)) - 1) * 100
        else:
            cagr_bond = (float(np.prod(1 + bond_daily)) ** (252 / n_days) - 1) * 100
    else:
        cagr_bond = 0.0

    eq_daily = np.zeros(n_days)
    for i in eq_idx:
        eq_daily += ret_hedged_mat[:, i] * weight_matrix[:, i]
    if n_days > 0:
        if is_short:
            cagr_eq = (float(np.prod(1 + eq_daily)) - 1) * 100
        else:
            cagr_eq = (float(np.prod(1 + eq_daily)) ** (252 / n_days) - 1) * 100
    else:
        cagr_eq = 0.0

    cagr_fx = fx_contrib
    cagr_ipo = params["ipo_alpha"] if not is_short else params["ipo_alpha"] * (n_days / 252)

    attribution = {
        "bond_contrib": cagr_bond,
        "eq_contrib":   cagr_eq,
        "fx_contrib":   cagr_fx,
        "ipo_contrib":  cagr_ipo,
        "total_cagr":   ann_open if not is_short else cumul,
    }

    return {
        "nav_open":             nav_open,
        "nav_hedged":           nav_hedged,
        "nav_benchmark":        nav_bench,
        "daily_returns":        port_open,
        "cagr":                 ann_open,
        "metric_display":       metric_open,
        "is_short_term":        is_short,
        "cagr_hedged":          ann_hedged,
        "mdd":                  mdd_val,
        "volatility":           vol_val,
        "sharpe":               sharpe_val,
        "fx_contribution":      fx_contrib,
        "cumulative_return":    cumul,
        "benchmark_cumulative": b_cumul,
        "yearly_portfolio":     calc_yearly_returns(nav_open),
        "yearly_benchmark":     calc_yearly_returns(nav_bench),
        "yearly_hedged":        calc_yearly_returns(nav_hedged),
        "drawdown":             calc_drawdown_series(nav_open),
        "weights":              weights,
        "category_weights":     cat_weights,
        "attribution":          attribution,
        "analysis_start":       returns.index[0],
        "analysis_end":         returns.index[-1],
        "total_days":           (returns.index[-1] - returns.index[0]).days,
        "trading_days":         len(returns),
    }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SIDEBAR UI (파라미터 제어)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def render_sidebar() -> tuple[dict, bool]:
    with st.sidebar:
        # 로그인 세션 정보 & 로그아웃
        c1, c2 = st.columns([3, 1])
        with c1:
            st.markdown(f"👤 **{st.session_state.get('username', '운용담당자')}**")
        with c2:
            if st.button("로그아웃", key="btn_logout"):
                for k in list(st.session_state.keys()):
                    del st.session_state[k]
                st.rerun()

        st.divider()
        st.header("⚙️ 시뮬레이션 파라미터")

        # ── 1. 분석 기간 (2025년 이후 및 단기 프리셋 지원) ──
        with st.expander("📅 분석 기간 설정 (단기/장기 자유 선택)", expanded=True):
            today = date.today()
            preset_options = [
                "2025년 이후 ~ 현재 (2025-01-01 ~ 오늘)",
                "최근 1개월 (초단기)",
                "최근 3개월 (단기)",
                "최근 6개월",
                "YTD (올해 연초 ~ 현재)",
                "최근 1년",
                "최근 3년",
                "최근 5년",
                "전체 기간 (2015-01-01 ~ 현재)",
                "직접 날짜 입력",
            ]
            preset = st.selectbox("⚡ 간편 기간 프리셋", preset_options, index=0)

            # 프리셋별 기본 날짜 설정
            if preset == "2025년 이후 ~ 현재 (2025-01-01 ~ 오늘)":
                d_start = date(2025, 1, 1)
                d_end = today
            elif preset == "최근 1개월 (초단기)":
                d_start = today - timedelta(days=30)
                d_end = today
            elif preset == "최근 3개월 (단기)":
                d_start = today - timedelta(days=90)
                d_end = today
            elif preset == "최근 6개월":
                d_start = today - timedelta(days=180)
                d_end = today
            elif preset == "YTD (올해 연초 ~ 현재)":
                d_start = date(today.year, 1, 1)
                d_end = today
            elif preset == "최근 1년":
                d_start = today - timedelta(days=365)
                d_end = today
            elif preset == "최근 3년":
                d_start = today - timedelta(days=365 * 3)
                d_end = today
            elif preset == "최근 5년":
                d_start = today - timedelta(days=365 * 5)
                d_end = today
            elif preset == "전체 기간 (2015-01-01 ~ 현재)":
                d_start = date(2015, 1, 1)
                d_end = today
            else:
                d_start = date(2025, 1, 1)
                d_end = today

            col_d1, col_d2 = st.columns(2)
            with col_d1:
                start_date = st.date_input(
                    "시작일",
                    value=d_start,
                    min_value=date(2000, 1, 1),
                    max_value=today,
                )
            with col_d2:
                end_date = st.date_input(
                    "종료일",
                    value=d_end,
                    min_value=date(2000, 1, 1),
                    max_value=today,
                )

            if start_date >= end_date:
                st.error("⚠️ 시작일은 종료일보다 이전이어야 합니다.")

        # ── 2. 투자대상 선택 (채권 & 지수 ETF) ──
        with st.expander("🏛️ 국고채 ETF 유니버스", expanded=True):
            st.caption("🇺🇸 **미국 국고채 ETF**")
            us_bonds = st.multiselect(
                "미국 국채", list(US_BOND.keys()), default=["IEF", "TLT"],
                format_func=lambda x: f"{x} - {US_BOND[x]}",
                label_visibility="collapsed",
            )

            st.caption("🇰🇷 **한국 국고채 ETF** (.KS 자동 매핑)")
            kr_bonds = st.multiselect(
                "한국 국고채", list(KR_BOND.keys()), default=["471230.KS"],
                format_func=lambda x: f"{x.replace('.KS','')} - {KR_BOND[x]}",
                label_visibility="collapsed",
            )

        with st.expander("📈 지수 ETF 유니버스 (미국·한국)", expanded=True):
            st.caption("🇺🇸 **미국 지수 ETF** (S&P500 / NASDAQ100)")
            us_equity = st.multiselect(
                "미국 지수 ETF", list(US_EQUITY.keys()), default=["SPY"],
                format_func=lambda x: f"{x} - {US_EQUITY[x]}",
                label_visibility="collapsed",
            )

            st.caption("🇰🇷 **한국 지수 ETF** (코스피200 / 코스닥150 / 국내상장 미국지수)")
            kr_equity = st.multiselect(
                "한국 지수 ETF", list(KR_EQUITY.keys()), default=["069500.KS"],
                format_func=lambda x: f"{x.replace('.KS','')} - {KR_EQUITY[x]}",
                label_visibility="collapsed",
            )

        # ── 3. 대체 및 현금성 자산 ──
        with st.expander("🏆 대체·현금성 자산", expanded=False):
            gold_on = st.toggle("Gold (GLDM) 편입", value=False)
            cash_ticker = st.selectbox(
                "현금성 자산 선택", list(CASH_OPTS.keys()),
                format_func=lambda x: (
                    f"{x.replace('.KS','')} - {CASH_OPTS[x]}"
                    if x != "BANK_DEPOSIT" else CASH_OPTS[x]
                ),
            )

        # ── 4. 투자비중 슬라이더 ──
        with st.expander("⚖️ 자산배분 비중 설정 (목표 8% 포트폴리오)", expanded=True):
            st.caption("💡 **설계 원칙**: 국채 90% 수준 + 지수 ETF 10% 수준")

            weight_us_bond = st.slider("미국 국고채 비중 (%)", 0, 100, 45, 5)
            weight_kr_bond = st.slider("한국 국고채 비중 (%)", 0, 100, 45, 5)
            weight_us_eq = st.slider("미국 지수 ETF 비중 (%)", 0, 30, 10, 1)
            weight_kr_eq = st.slider("한국 지수 ETF 비중 (%)", 0, 30, 0, 1)
            weight_alt_cash = st.slider("대체(Gold)/현금성 자산 비중 (%)", 0, 20, 0, 1)

            total_raw_w = weight_us_bond + weight_kr_bond + weight_us_eq + weight_kr_eq + weight_alt_cash
            if total_raw_w == 100:
                st.success(f"합계 비중: **{total_raw_w}%** (정상)")
            else:
                st.info(f"합계: **{total_raw_w}%** → 포트폴리오 편입 시 **100% 자동 정규화** 적용")

        # ── 5. 공모주 수익 기여도(Alpha) ──
        with st.expander("💰 공모주 수익 기여도 (Alpha)", expanded=False):
            ipo_alpha = st.slider(
                "공모주 연간 Alpha 가산 (%p)", 0.0, 1.0, 0.0, 0.05,
                help="일할 가산하여 포트폴리오 일간 수익률에 반영됩니다. (목표 모델: 0~1%대)"
            )

        # ── 6. 동적 TAA (전술적 자산배분) ──
        with st.expander("🔄 동적 TAA (전술적 자산배분) 토글", expanded=False):
            st.caption("**[전략 1] 기술적 지표 14일 RSI 과매도 탄력 운용**")
            rsi_on = st.toggle("RSI 과매도 TAA 활성화", value=False)
            rsi_period = 14; rsi_entry = 30; rsi_exit = 60; rsi_max = 20
            if rsi_on:
                rsi_period = int(st.number_input("RSI 산출 기간", 5, 30, 14, key="rsi_p"))
                rsi_entry  = int(st.number_input("과매도 진입 RSI (기본 30)", 10, 45, 30, key="rsi_e"))
                rsi_exit   = int(st.number_input("탈출 기준 RSI (기본 60)", 50, 80, 60, key="rsi_x"))
                rsi_max    = int(st.number_input("최대 유지 영업일 (기본 20)", 5, 60, 20, key="rsi_m"))

            st.caption("**[전략 2] 상장기업 영업이익 턴어라운드 적극 투자**")
            ta_on = st.toggle("턴어라운드 모드 활성화 (주식 비중 30% 확대)", value=False)
            ta_years: list[int] = []
            if ta_on:
                yr_range = list(range(2015, date.today().year + 1))
                ta_years = st.multiselect("적극 투자 국면 연도 선택", yr_range, default=[])

        # ── 7. 환율 및 통화 비교 제어 ──
        with st.expander("💱 환율 및 통화 비교 제어", expanded=True):
            st.caption("기본값: **환오픈 (USD 노출)** - 연평균 3% 이상 원화 약세/달러 강세 기대 반영")
            hedge_ratio = st.slider(
                "환헤지 비중 (%)", 0, 100, 0, 5,
                help="0% = 100% 환오픈 (기본값), 100% = 완전 환헤지"
            )
            show_hedged = st.checkbox("환헤지(USD) 수익률 비교 라인 표시", value=True)

        st.divider()
        run_clicked = st.button("🚀 시뮬레이션 재실행", type="primary", use_container_width=True)

    params = {
        "start_date":       start_date,
        "end_date":         end_date,
        "us_bonds":         us_bonds,
        "kr_bonds":         kr_bonds,
        "us_equity":        us_equity,
        "kr_equity":        kr_equity,
        "gold_enabled":     gold_on,
        "cash_ticker":      cash_ticker,
        "weight_us_bond":   weight_us_bond,
        "weight_kr_bond":   weight_kr_bond,
        "weight_us_eq":     weight_us_eq,
        "weight_kr_eq":     weight_kr_eq,
        "weight_alt_cash":  weight_alt_cash,
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
#  MAIN DASHBOARD DISPLAY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def render_dashboard(res: dict, show_hedged: bool):
    st.title("🏛️ 국채·지수 ETF 혼합형 펀드 퀀트 백테스팅")
    p_start = res["analysis_start"].strftime("%Y-%m-%d")
    p_end   = res["analysis_end"].strftime("%Y-%m-%d")

    is_short = res.get("is_short_term", False)
    trading_days = res.get("trading_days", 0)
    total_days = res.get("total_days", 0)

    st.caption(
        f"분석 데이터 구간: **{p_start} ~ {p_end}** ({total_days}일, {trading_days}영업일) | 통화 기준: **KRW (원화)**"
    )

    if is_short:
        st.markdown(
            f"""
            <div class="short-banner">
            ⚡ <b>단기 모니터링 모드 활성화</b>: 조회 기간이 1년 미만({trading_days}영업일)입니다.
            기간 단순 누적 수익률을 중심으로 분석하며, 연환산(참고치)이 함께 병기됩니다.
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ────────────────────────────────────────────────────────────────
    # [1] 상단 KPI 메트릭 카드 5개
    # ────────────────────────────────────────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        if is_short:
            st.metric(
                "기간 단순 수익률",
                f"{res['cumulative_return']:+.2f}%",
                delta=f"연환산 {res['cagr']:+.2f}%",
            )
        else:
            diff_target = res["cagr"] - 8.0
            st.metric(
                "연평균 복리수익률 (CAGR)",
                f"{res['cagr']:.2f}%",
                delta=f"목표 8% 대비 {diff_target:+.2f}%p",
            )
    with k2:
        st.metric("최대 낙폭 (MDD)", f"{res['mdd']:.2f}%")
    with k3:
        st.metric(
            "변동성 / 샤프지수",
            f"{res['volatility']:.2f}%",
            delta=f"Sharpe {res['sharpe']:.2f}",
            delta_color="off",
        )
    with k4:
        sign = "+" if res["fx_contribution"] >= 0 else ""
        label_fx = "환차익 기여도" if not is_short else "환차익 기여(연환산)"
        st.metric(label_fx, f"{sign}{res['fx_contribution']:.2f}%p")
    with k5:
        st.metric(
            "누적 수익률 vs BM",
            f"{res['cumulative_return']:.1f}%",
            delta=f"S&P500(KRW) {res['benchmark_cumulative']:.1f}%",
            delta_color="off",
        )

    st.divider()

    # ────────────────────────────────────────────────────────────────
    # [2] 목표수익률 8%대 달성도 & 성과 기여도 분해 (Performance Attribution)
    # ────────────────────────────────────────────────────────────────
    st.subheader("🎯 목표수익률 8%대 달성도 및 성과 기여도 분해 (Attribution Analysis)")
    st.markdown(
        """
        자산운용 펀드 상품 기획 시 설계된 **4대 핵심 기대수익 구조**와 실제 백테스팅 기간 동안의 **실현 기여도**를 정밀 비교합니다.
        """
    )

    attr = res["attribution"]

    a1, a2, a3, a4, a5 = st.columns(5)
    with a1:
        st.metric("① 국채 ETF 기여도", f"{attr['bond_contrib']:+.2f}%p", help="목표 모델: 3~4%대 (국채 90% × 채권 연수익 4~5%)")
        st.caption("📌 **목표 모델**: 3.0~4.0%p")
    with a2:
        st.metric("② 지수 ETF 기여도", f"{attr['eq_contrib']:+.2f}%p", help="목표 모델: 0~3%대 (지수 10% × 주식 연수익 0~30%)")
        st.caption("📌 **목표 모델**: 0.0~3.0%p")
    with a3:
        st.metric("③ 환차익 기여도", f"{attr['fx_contrib']:+.2f}%p", help="목표 모델: 3~5%대 (미국 자산 환노출, 연평균 3% 이상 원화 약세)")
        st.caption("📌 **목표 모델**: 3.0~5.0%p")
    with a4:
        st.metric("④ 공모주 Alpha", f"{attr['ipo_contrib']:+.2f}%p", help="목표 모델: 0~1%대 (연 0~1%p 가산)")
        st.caption("📌 **목표 모델**: 0.0~1.0%p")
    with a5:
        label_total = "합산 실현 수익률" if is_short else "합산 실현 CAGR"
        st.metric(label_total, f"{attr['total_cagr']:.2f}%", delta=f"{attr['total_cagr'] - 8.0:+.2f}%p vs 8.0% 목표")
        st.caption("🏆 **목표 종합**: **8.0% ~ 10.0%대**")

    # 성과 기여도 바 차트
    fig_attr = go.Figure(go.Bar(
        x=["① 국채 ETF", "② 지수 ETF", "③ 환차익(USD/KRW)", "④ 공모주 Alpha", "합산 실현치"],
        y=[attr['bond_contrib'], attr['eq_contrib'], attr['fx_contrib'], attr['ipo_contrib'], attr['total_cagr']],
        marker=dict(color=["#1976D2", "#388E3C", "#F57C00", "#7B1FA2", "#D32F2F"]),
        text=[f"{v:+.2f}%p" if i < 4 else f"{v:.2f}%" for i, v in enumerate(
            [attr['bond_contrib'], attr['eq_contrib'], attr['fx_contrib'], attr['ipo_contrib'], attr['total_cagr']]
        )],
        textposition="outside",
    ))
    fig_attr.add_hline(y=8.0, line_dash="dash", line_color="#E53935", annotation_text="목표 수익률 8.0%")
    fig_attr.update_layout(
        title="원천별 수익 기여도 분해 (%p)",
        template="plotly_white",
        yaxis_title="수익 기여도 (%p)",
        height=320,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    st.plotly_chart(fig_attr, use_container_width=True)

    st.divider()

    # ────────────────────────────────────────────────────────────────
    # [3] 시각화 차트 1 & 2
    # ────────────────────────────────────────────────────────────────
    st.subheader("📈 Chart 1 — 누적 자산가치(NAV) 추이")
    fig_nav = go.Figure()
    fig_nav.add_trace(go.Scatter(
        x=res["nav_open"].index, y=res["nav_open"].values,
        name="혼합형 펀드 (환오픈, 기본)",
        line=dict(color="#1565C0", width=2.5),
    ))
    if show_hedged:
        fig_nav.add_trace(go.Scatter(
            x=res["nav_hedged"].index, y=res["nav_hedged"].values,
            name="혼합형 펀드 (환헤지 100%)",
            line=dict(color="#E65100", width=2, dash="dash"),
        ))
    fig_nav.add_trace(go.Scatter(
        x=res["nav_benchmark"].index, y=res["nav_benchmark"].values,
        name="S&P500 벤치마크 (KRW 원화)",
        line=dict(color="#2E7D32", width=1.5, dash="dot"),
    ))
    fig_nav.update_layout(
        template="plotly_white",
        hovermode="x unified",
        yaxis_title="기준 자산가치 (시작 = 100)",
        legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center"),
        margin=dict(l=10, r=10, t=30, b=10),
        height=450,
    )
    st.plotly_chart(fig_nav, use_container_width=True)

    st.subheader("📉 Chart 2 — 낙폭 추이 (Underwater Plot / Drawdown %)")
    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(
        x=res["drawdown"].index, y=res["drawdown"].values,
        fill="tozeroy", name="낙폭 (Drawdown %)",
        line=dict(color="#D32F2F", width=1.2),
        fillcolor="rgba(211,47,47,0.18)",
    ))
    fig_dd.update_layout(
        template="plotly_white",
        hovermode="x unified",
        yaxis_title="Drawdown (%)",
        margin=dict(l=10, r=10, t=10, b=10),
        height=280,
    )
    st.plotly_chart(fig_dd, use_container_width=True)

    st.divider()

    # ────────────────────────────────────────────────────────────────
    # [4] 데이터 테이블
    # ────────────────────────────────────────────────────────────────
    t1, t2 = st.columns(2)
    with t1:
        st.subheader("📋 테이블 1 — 성과 및 리스크 요약")
        bench_ret = res["nav_benchmark"].pct_change().dropna()
        cagr_label = "연평균 복리수익률 (CAGR)" if not is_short else "기간 누적수익률 (연환산)"
        summary = pd.DataFrame({
            "지표": ["누적 수익률", cagr_label, "연환산 변동성", "샤프 지수 (Rf=3%)", "최대 낙폭 (MDD)"],
            "혼합형 펀드 (환오픈)": [
                f"{res['cumulative_return']:.2f}%",
                f"{res['cagr']:.2f}%",
                f"{res['volatility']:.2f}%",
                f"{res['sharpe']:.2f}",
                f"{res['mdd']:.2f}%",
            ],
            "S&P500 벤치마크(KRW)": [
                f"{res['benchmark_cumulative']:.2f}%",
                f"{calc_returns_and_cagr(res['nav_benchmark'])[1]:.2f}%",
                f"{calc_volatility(bench_ret):.2f}%",
                f"{calc_sharpe(bench_ret):.2f}",
                f"{calc_mdd(res['nav_benchmark']):.2f}%",
            ],
        })
        st.dataframe(summary, hide_index=True, use_container_width=True)

    with t2:
        st.subheader("📅 테이블 2 — 연도별 수익률 (%)")
        yearly = pd.DataFrame({
            "혼합형 펀드": res["yearly_portfolio"].round(2),
            "S&P500(KRW)": res["yearly_benchmark"].round(2),
        })
        if show_hedged:
            yearly["환헤지 포트폴리오"] = res["yearly_hedged"].round(2)
        yearly.index.name = "연도"
        st.dataframe(yearly, use_container_width=True)

    st.divider()

    # ────────────────────────────────────────────────────────────────
    # [5] 자산배분 유효 비중 상세
    # ────────────────────────────────────────────────────────────────
    with st.expander("🔍 포트폴리오 유효 자산배분 비중 상세", expanded=False):
        c_cat, c_asset = st.columns(2)
        with c_cat:
            st.markdown("##### 📌 자산군별 실효 비중")
            cat_df = pd.DataFrame([
                {"자산군": k, "비중(%)": f"{v * 100:.2f}%"} for k, v in res["category_weights"].items()
            ])
            st.dataframe(cat_df, hide_index=True, use_container_width=True)

        with c_asset:
            st.markdown("##### 📌 개별 종목별 실효 비중")
            w_df = pd.DataFrame(
                [{"종목": k, "비중(%)": round(v * 100, 2)} for k, v in res["weights"].items()]
            ).sort_values("비중(%)", ascending=False).reset_index(drop=True)
            st.dataframe(w_df, hide_index=True, use_container_width=True)

    # ────────────────────────────────────────────────────────────────
    # [6] 엑셀 다운로드 (openpyxl 활용)
    # ────────────────────────────────────────────────────────────────
    nav_df = pd.DataFrame({
        "Date":        res["nav_open"].index,
        "NAV_환오픈":   res["nav_open"].values.round(4),
        "NAV_환헤지":   res["nav_hedged"].values.round(4),
        "NAV_벤치마크": res["nav_benchmark"].values.round(4),
    })
    yearly_exp = pd.DataFrame({
        "연도":            res["yearly_portfolio"].index,
        "혼합형펀드(%)":    res["yearly_portfolio"].values.round(2),
        "S&P500(KRW)(%)": res["yearly_benchmark"].values.round(2),
    })
    attr_df = pd.DataFrame({
        "구분": ["① 국채 ETF", "② 지수 ETF", "③ 환차익(USD/KRW)", "④ 공모주 Alpha", "합산 실현치"],
        "설계 목표 모델": ["3.0 ~ 4.0%대", "0.0 ~ 3.0%대", "3.0 ~ 5.0%대", "0.0 ~ 1.0%대", "8.0 ~ 10.0%대"],
        "백테스팅 실현 기여도(%p)": [
            round(attr['bond_contrib'], 2),
            round(attr['eq_contrib'], 2),
            round(attr['fx_contrib'], 2),
            round(attr['ipo_contrib'], 2),
            round(attr['total_cagr'], 2),
        ],
    })

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        summary.to_excel(w, sheet_name="성과요약", index=False)
        attr_df.to_excel(w, sheet_name="목표수익률기여도분해", index=False)
        yearly_exp.to_excel(w, sheet_name="연도별수익률", index=False)
        nav_df.to_excel(w, sheet_name="일별NAV", index=False)

    st.download_button(
        label="📥 엑셀 다운로드 (국채_ETF_혼합형펀드_백테스팅_결과.xlsx)",
        data=buf.getvalue(),
        file_name="국채_ETF_혼합형펀드_백테스팅_결과.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MAIN ENTRY POINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def main():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    if not st.session_state.get("authenticated"):
        show_login()
        return

    params, run_clicked = render_sidebar()

    if run_clicked:
        has_any = (
            params["us_bonds"] or params["kr_bonds"]
            or params["us_equity"] or params["kr_equity"]
            or params["gold_enabled"]
            or (params["cash_ticker"] and params["weight_alt_cash"] > 0)
        )
        if not has_any:
            st.error("❌ 유니버스에서 최소 하나의 ETF 종목을 선택하세요.")
            return

        with st.spinner("📊 퀀트 백테스팅 및 포트폴리오 시뮬레이션 계산 중..."):
            results = run_backtest(params)

        if results is not None:
            st.session_state["results"] = results
            st.session_state["show_hedged"] = params["show_hedged_line"]

    if "results" in st.session_state:
        render_dashboard(
            st.session_state["results"],
            st.session_state.get("show_hedged", True),
        )
    else:
        st.markdown("## 🏛️ 국채·지수 ETF 혼합형 펀드 퀀트 백테스팅 대시보드")
        st.info("👈 좌측 사이드바에서 **분석 기간(2025년 이후/단기 프리셋 지원) 및 ETF 비중**을 설정하고 **🚀 시뮬레이션 재실행** 버튼을 누르세요.")
        st.markdown(
            """
            ### 🎯 목표수익률 8%대 펀드 포트폴리오 구조
            | 수익 원천 | 설계 목표 모델 | 설명 |
            |---|---|---|
            | **국채 ETF** | **3 ~ 4%대** | 채권 비중 약 90% × 채권 연수익 4~5% |
            | **지수 ETF** | **0 ~ 3%대** | 주식 비중 약 10% × 지수 연수익 0~30% |
            | **환차익** | **3 ~ 5%대** | 미국 국채/지수 ETF 환노출 (연평균 3% 이상 원화 약세 기대) |
            | **공모주 (Alpha)** | **0 ~ 1%대** | 공모주 펀드 전략 Alpha 일할 가산 |
            | **합산 기대수익률** | **연 8.0% ~ 10.0%대** | 안정적 채권 이자 + 주식 알파 + 달러 환차익 하이브리드 추구 |
            """
        )

if __name__ == "__main__":
    main()
