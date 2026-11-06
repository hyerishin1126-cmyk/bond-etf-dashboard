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
    - 날짜는 2000-01-01부터 전체 구간 선택 가능
    - 실제 조회 시작일은 선택 종목 중 가장 늦게 상장한 종목의 상장일(데이터 첫 거래일)로 자동 보정 + 안내 팝업
    - 프리셋: 전체 기간 / 최근 2년 / 최근 1년 / 연초 이후(YTD) / 사용자 직접 지정
    - 1년 미만 구간은 단기 모니터링 모드(기간 누적 수익률 중심)로 자동 전환
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

정확도 개선 (v2)
-----------------------------------------------------
① TAA 시차 보정: RSI 신호는 '알 수 있는 시점' 이후 다음 영업일 수익률부터 적용
   (한국 영업일 기준이면 미국 종가는 다음 한국 영업일에야 확인 가능하므로 1영업일 추가 지연)
② 단일 기준 캘린더 + 달력일 기준 연환산:
   - 한국 종목이 있으면 '한국 영업일', 없으면 '미국 영업일'을 기준 캘린더로 사용
     (다른 시장 가격은 직전 종가로 as-of 정렬 → 휴장일 0% 수익률 왜곡 제거)
   - 은대 이자·공모주 Alpha·무위험수익률은 실제 경과 달력일(dt/365)로 일할
   - 변동성·샤프의 연환산 계수는 실제 관측 빈도(연간 영업일 수)로 산출
④ 환헤지 비용 반영: 헤지 부분에 (원화 단기금리 − 달러 단기금리) × dt/365 의 금리차(carry) 반영
   - 자동: 달러 ^IRX(미 T-bill 3M), 원화 FRED IR3TIB01KRM156N(한국 3M 금리) / 실패 시 수동값
⑤ 성과 기여도 분해: 일별 기여도 × 직전 NAV 가중으로 연결(linking) → 항목 합계 = 총 수익률 정확히 일치
   - 금·현금성, 환헤지 손익(carry) 항목 추가, 단기/장기 단위 통일
⑥ 총수익(Total Return) 데이터: 분할 반영 종가 + yfinance 분배금 재투자로 직접 산출
(부수 수정) NAV에 기준일(=100)을 포함하여 첫 영업일 수익률이 누락되지 않도록 수정
"""

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import requests
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

# 국내상장이지만 기초자산이 달러 자산이라 원화 가격에 환율 효과가 섞여 있는 ETF
KR_LISTED_US_FX = {"360750.KS", "133690.KS", "379800.KS"}

ALL_NAMES = {**US_BOND, **KR_BOND, **US_EQUITY, **KR_EQUITY, **CASH_OPTS,
             "GLDM": "SPDR Gold MiniShares", "SPY": US_EQUITY["SPY"]}

# ── 분석 기간 ──
# 날짜 선택은 전체 구간을 허용하고, 실제 조회 시작일은 '선택 종목 중 가장 늦게 상장한 종목'의
# 상장일(=데이터 첫 거래일)로 자동 보정한다.
DATA_FLOOR = date(2000, 1, 1)   # 날짜 선택기에서 고를 수 있는 가장 이른 날짜
PARTIAL_YEAR_GRACE_DAYS = 7     # 연초 휴장으로 첫 거래일이 며칠 밀린 해는 '전체 연도'로 취급

PRESET_ALL = "전체 기간 (선택 종목 공통 시작일 ~ 현재)"
PRESET_2Y = "최근 2년"
PRESET_1Y = "최근 1년"
PRESET_YTD = "연초 이후 (YTD)"
PRESET_CUSTOM = "사용자 직접 지정"
PERIOD_PRESETS = [PRESET_ALL, PRESET_2Y, PRESET_1Y, PRESET_YTD, PRESET_CUSTOM]


def clamp_period_date(d: date, today: date) -> date:
    """선택 가능한 범위 [DATA_FLOOR, today] 안으로 보정."""
    return min(max(d, DATA_FLOOR), today)


def preset_date_range(preset: str, today: date) -> tuple[date, date] | None:
    """프리셋별 (시작일, 종료일). '사용자 직접 지정'은 None (현재 선택값 유지)."""
    if preset == PRESET_ALL:
        start = DATA_FLOOR          # 실행 시 가장 늦게 상장한 종목의 상장일로 보정됨
    elif preset == PRESET_2Y:
        start = today - timedelta(days=730)
    elif preset == PRESET_1Y:
        start = today - timedelta(days=365)
    elif preset == PRESET_YTD:
        start = date(today.year, 1, 1)
    else:
        return None
    return clamp_period_date(start, today), today


def display_name(t: str) -> str:
    """팝업·안내용 종목 표기: 'KODEX 국고채10년액티브'(471230)"""
    code = t.replace(".KS", "").replace(".KQ", "")
    name = ALL_NAMES.get(t, code).split(" (")[0]
    return f"'{name}'({code})" if name != code else f"'{code}'"


def yearly_labels(years: pd.Index, start: pd.Timestamp, end: pd.Timestamp,
                  start_is_listing: bool = False) -> tuple[list[str], list[str]]:
    """
    연도별 수익률 표의 행 이름과 행별 비고 (전체 연도면 빈 문자열).
    - 첫 해가 연중에 시작하면 '2023년* (상장 이후)' 또는 '2025년* (11-06 이후)'로 표시
    - 마지막 해가 연중에 끝나면 '2026년† (YTD)'로 표시
    """
    labels, notes = [], []
    for yr in years:
        yr = int(yr)
        first_partial = yr == start.year and start > pd.Timestamp(yr, 1, 1) + pd.Timedelta(days=PARTIAL_YEAR_GRACE_DAYS)
        last_partial = yr == end.year and end < pd.Timestamp(yr, 12, 24)
        if first_partial:
            tag = "상장 이후" if start_is_listing else f"{start:%m-%d} 이후"
            labels.append(f"{yr}년* ({tag})")
            year_end = min(end, pd.Timestamp(yr, 12, 31))
            notes.append(f"* {yr}년은 전체 연도가 아닌 {start:%Y-%m-%d} ~ {year_end:%Y-%m-%d} 구간의 기간 수익률입니다.")
        elif last_partial:
            labels.append(f"{yr}년† (YTD)")
            notes.append(f"† {yr}년은 {yr}-01-01 ~ {end:%Y-%m-%d} 구간의 기간 수익률입니다.")
        else:
            labels.append(f"{yr}년")
            notes.append("")
    return labels, notes


def show_start_adjust_popup(message: str):
    """조회 시작일 보정 팝업 (Streamlit 버전에 따라 st.dialog → experimental_dialog → 경고 박스)."""
    dialog = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
    if dialog is None:
        st.warning(f"📅 {message}")
        return

    @dialog("📅 조회 시작일 수정")
    def _popup():
        st.write(message)
        if st.button("확인", type="primary", use_container_width=True):
            st.rerun()

    _popup()


BANK_RATE = 0.0253          # 은대 연 금리
DAY_COUNT = 365.0           # 이자 일할 기준 (원화 관행 ACT/365)
RF_ANNUAL = 0.03            # 샤프 지수 무위험수익률
ASOF_TOLERANCE = pd.Timedelta(days=10)   # 다른 시장 종가를 가져올 때 허용하는 최대 공백

# 자동 금리 소스
FRED_KRW_3M = "IR3TIB01KRM156N"   # 한국 3개월 금리 (OECD, 월별)
FRED_USD_3M = "DTB3"              # 미 T-bill 3개월 (일별) — ^IRX 실패 시 대체


def is_kr_ticker(t: str) -> bool:
    return t.endswith(".KS") or t.endswith(".KQ")


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
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_raw(ticker: str, start: str, end: str) -> pd.DataFrame:
    """
    분할만 반영된 종가(close)와 분배금(div)을 함께 다운로드.
    배당 재투자는 build_total_return()에서 직접 계산한다.
    (yfinance end는 미포함이므로 +1일)
    """
    end_incl = (pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        df = yf.Ticker(ticker).history(
            start=start, end=end_incl, auto_adjust=False, actions=True,
        )
    except Exception:
        return pd.DataFrame()
    if df is None or df.empty or "Close" not in df.columns:
        return pd.DataFrame()

    out = pd.DataFrame(index=df.index)
    out["close"] = pd.to_numeric(df["Close"], errors="coerce").astype("float64")
    if "Dividends" in df.columns:
        out["div"] = pd.to_numeric(df["Dividends"], errors="coerce").fillna(0.0).astype("float64")
    else:
        out["div"] = 0.0

    idx = pd.DatetimeIndex(out.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)        # 각 거래소 현지 날짜 유지
    out.index = idx.normalize()
    out = out[~out.index.duplicated(keep="last")].sort_index()
    out = out[out["close"] > 0].dropna(subset=["close"])
    return out


@st.cache_data(ttl=43200, show_spinner=False)
def fetch_fred_series(series_id: str) -> pd.Series:
    """FRED 공개 CSV (API 키 불필요). 실패 시 빈 Series."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        s = pd.to_numeric(df.iloc[:, -1], errors="coerce")
        s.index = pd.to_datetime(df.iloc[:, 0], errors="coerce")
        s = s[s.index.notna()].dropna().sort_index()
        return s.astype("float64")
    except Exception:
        return pd.Series(dtype="float64")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ⑥ TOTAL RETURN (분배금 재투자)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def build_total_return(raw: pd.DataFrame) -> pd.Series:
    """총수익 지수 = 100 × Π (P_t + D_t) / P_{t-1}  (P: 분할 반영 종가, D: yfinance 분배금)"""
    close = raw["close"]
    div = raw["div"].fillna(0.0)
    gross = (close + div) / close.shift(1)
    gross.iloc[0] = 1.0
    return (100.0 * gross.cumprod()).astype("float64")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ④ 금리 (헤지 carry)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _asof(s: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    s = s.sort_index()
    out = s.reindex(index, method="ffill")
    return out.bfill().ffill()


def get_rate_series(index: pd.DatetimeIndex, mode: str,
                    manual_kr: float, manual_us: float) -> tuple[pd.Series, pd.Series, str]:
    """원화·달러 단기금리(연 %)를 index 위에 as-of 정렬. 실패 시 수동값."""
    notes = []
    kr = us = None
    if mode == "자동":
        start = (index[0] - pd.Timedelta(days=120)).strftime("%Y-%m-%d")
        end = index[-1].strftime("%Y-%m-%d")
        irx = fetch_raw("^IRX", start, end)
        if not irx.empty:
            us = irx["close"]
            notes.append("USD 3M: ^IRX(미 T-bill 13주)")
        else:
            fr = fetch_fred_series(FRED_USD_3M)
            if not fr.empty:
                us = fr
                notes.append(f"USD 3M: FRED {FRED_USD_3M}")
        k = fetch_fred_series(FRED_KRW_3M)
        if not k.empty:
            kr = k
            lag_days = (index[-1] - k.index[-1]).days
            stale = f", 최근 {lag_days}일은 마지막 월값 유지" if lag_days > 45 else ""
            notes.append(f"KRW 3M: FRED {FRED_KRW_3M}(월별{stale})")

    if us is None:
        us = pd.Series(manual_us, index=index)
        notes.append(f"USD: 수동 {manual_us:.2f}%")
    if kr is None:
        kr = pd.Series(manual_kr, index=index)
        notes.append(f"KRW: 수동 {manual_kr:.2f}%")
    if mode == "자동" and any("수동" in n for n in notes):
        notes.append("⚠️ 자동 조회 일부 실패 → 수동값 대체")
    return _asof(kr, index), _asof(us, index), " · ".join(notes)


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

def calc_periods_per_year(index: pd.DatetimeIndex) -> float:
    """실제 관측 빈도(연간 영업일 수). 3개월 미만 구간은 표본이 적어 252로 고정."""
    n = len(index) - 1
    days = (index[-1] - index[0]).days if len(index) > 1 else 0
    if n <= 0 or days < 90:
        return 252.0
    return n / (days / 365.25)

def calc_volatility(returns: pd.Series, periods_per_year: float = 252.0) -> float:
    """연환산 변동성 (%)."""
    if len(returns) < 2:
        return 0.0
    return float(returns.std() * np.sqrt(periods_per_year) * 100)

def calc_sharpe(returns: pd.Series, dt_days: pd.Series | None = None,
                periods_per_year: float = 252.0, rf_annual: float = RF_ANNUAL) -> float:
    """샤프 지수 (연환산). 무위험수익률은 실제 경과 달력일로 일할."""
    if len(returns) < 2:
        return 0.0
    if dt_days is None:
        rf = (1 + rf_annual) ** (1 / periods_per_year) - 1
    else:
        rf = (1 + rf_annual) ** (dt_days.reindex(returns.index).fillna(1.0) / DAY_COUNT) - 1
    excess = returns - rf
    std = excess.std()
    if std == 0 or np.isnan(std):
        return 0.0
    return float((excess.mean() / std) * np.sqrt(periods_per_year))

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
    """RSI 과매도 진입/탈출 시그널 (1=진입, 0=미진입). 값은 '해당일 종가 시점'에 확정."""
    signal = np.zeros(len(rsi), dtype="float64")
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

def align_signal_no_lookahead(sig_native: pd.Series, price_index: pd.DatetimeIndex,
                              native_is_us: bool, calendar_is_kr: bool) -> pd.Series:
    """
    ① 시차 보정.
    sig_native[d] 는 d일 종가 시점에 확정된다.
    - 미국 신호를 한국 캘린더에 쓰는 경우: 미국 d일 종가는 한국 d+1일 아침에 확인 → 가용일 +1일
    - 반환값은 '수익률 행(t)'에 적용할 신호: t-1 시점(직전 종가)까지 확인 가능한 신호
    """
    s = sig_native.copy()
    if native_is_us and calendar_is_kr:
        s.index = s.index + pd.Timedelta(days=1)
    avail = s.reindex(price_index, method="ffill").fillna(0.0)
    return avail.shift(1).iloc[1:].fillna(0.0)

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
    cash_ok = cash_tk and cash_tk in available

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
    start_req = pd.Timestamp(params["start_date"])
    end_ts = pd.Timestamp(params["end_date"])
    e_str = end_ts.strftime("%Y-%m-%d")
    floor_str = DATA_FLOOR.strftime("%Y-%m-%d")     # 상장일 파악을 위해 항상 전체 이력 조회 (종목별 캐시)

    # ── 0. 편입 후보 (비중 0% 자산군은 공통 구간을 줄이지 않도록 제외) ──
    w_raw = {
        "us_bond": params["weight_us_bond"], "kr_bond": params["weight_kr_bond"],
        "us_eq": params["weight_us_eq"], "kr_eq": params["weight_kr_eq"],
        "alt": params["weight_alt_cash"],
    }
    if not params["us_bonds"]:
        w_raw["kr_bond"] += w_raw["us_bond"]       # _calc_weights의 미국채→한국채 이전 규칙과 동일

    group: dict[str, str] = {}      # ticker → 기여도 버킷 (bond / equity / alt)
    for t in params["us_bonds"]:
        if w_raw["us_bond"] > 0: group[t] = "bond"
    for t in params["kr_bonds"]:
        if w_raw["kr_bond"] > 0: group[t] = "bond"
    for t in params["us_equity"]:
        if w_raw["us_eq"] > 0: group[t] = "equity"
    for t in params["kr_equity"]:
        if w_raw["kr_eq"] > 0: group[t] = "equity"
    if w_raw["alt"] > 0:
        if params["gold_enabled"]:
            group["GLDM"] = "alt"
        if params["cash_ticker"]:
            group[params["cash_ticker"]] = "alt"
    if not group:
        st.error("❌ 비중이 0%보다 큰 자산군에서 최소 하나의 종목을 선택하세요.")
        return None

    us_set = set(params["us_bonds"]) | set(params["us_equity"]) | {"GLDM"}
    market_tk = [t for t in group if t != "BANK_DEPOSIT"]

    # ── 1. 시세 + 분배금 수집 (⑥ 총수익 직접 산출) ──
    raw: dict[str, pd.DataFrame] = {}
    for t in sorted(set(market_tk + ["SPY"])):
        df = fetch_raw(t, floor_str, e_str)
        if not df.empty:
            raw[t] = df

    missing = [t for t in market_tk if t not in raw]
    if missing:
        st.warning(
            f"⚠️ 조회 종료일({end_ts:%Y-%m-%d})까지 데이터가 없어 제외한 종목(상장 전이거나 시세 조회 실패): "
            f"{', '.join(display_name(t) for t in missing)}"
        )
    avail_mkt = [t for t in market_tk if t in raw]
    pt = avail_mkt + (["BANK_DEPOSIT"] if "BANK_DEPOSIT" in group else [])
    if not pt:
        st.error("❌ 유효한 포트폴리오 종목이 존재하지 않습니다.")
        return None

    tr: dict[str, pd.Series] = {}
    for t, df in raw.items():
        tr[t] = build_total_return(df)

    # ── 1-1. 조회 시작일 보정: 선택 종목 중 가장 늦게 상장한 종목 기준 ──
    #   상장일 = 데이터 첫 거래일. 달러 자산이 있으면 USD/KRW 환율 데이터 시작일도 함께 고려.
    fx_df = fetch_raw("KRW=X", floor_str, e_str)
    first_dates: dict[str, pd.Timestamp] = {t: raw[t].index[0] for t in avail_mkt}
    if any(t in us_set for t in avail_mkt) and not fx_df.empty:
        first_dates["KRW=X"] = fx_df.index[0]

    start_ts = start_req
    start_adjustment = None
    if first_dates:
        latest = max(first_dates.values())
        if latest > start_req:
            causes = [t for t, d in first_dates.items() if d == latest]
            stock_causes = [t for t in causes if t != "KRW=X"]
            if stock_causes:
                who = ", ".join(display_name(t) for t in stock_causes)
                message = f"{who} 상장일이 {latest:%Y-%m-%d} 이므로 조회 시작일을 수정했습니다."
            else:
                message = f"USD/KRW 환율 데이터 시작일이 {latest:%Y-%m-%d} 이므로 조회 시작일을 수정했습니다."
            start_ts = latest
            start_adjustment = {
                "requested": start_req.date(), "new_start": latest.date(),
                "causes": causes, "message": message,
            }
            if start_ts >= end_ts:
                st.error(
                    f"❌ {message.replace(' 이므로 조회 시작일을 수정했습니다.', '')}로, 조회 종료일"
                    f"({end_ts:%Y-%m-%d}) 이후입니다. 종료일을 늦추거나 종목을 변경하세요."
                )
                return None

    # ── 2. 기준 캘린더 (② 한국 종목이 있으면 한국 영업일) ──
    kr_mkt = [t for t in avail_mkt if is_kr_ticker(t)]
    calendar_is_kr = bool(kr_mkt)
    ref = kr_mkt if calendar_is_kr else (avail_mkt or ["SPY"])
    ref = [t for t in ref if t in raw]
    if not ref:
        st.error("❌ 기준 캘린더를 만들 시세가 없습니다.")
        return None
    cal = raw[ref[0]].index
    for t in ref[1:]:
        cal = cal.union(raw[t].index)
    cal = cal[(cal >= start_ts) & (cal <= end_ts)]
    calendar_label = "한국 영업일" if calendar_is_kr else "미국 영업일"

    cols = list(dict.fromkeys(avail_mkt + (["SPY"] if "SPY" in tr else [])))
    prices = pd.DataFrame(
        {t: tr[t].reindex(cal, method="ffill", tolerance=ASOF_TOLERANCE) for t in cols},
        index=cal,
    )
    # 상장 전 구간이 ffill로 채워지지 않도록: 원시 데이터 첫날 이전은 NaN 유지
    for t in cols:
        prices.loc[prices.index < tr[t].index[0], t] = np.nan

    first_valid = max(prices[c].first_valid_index() or pd.Timestamp.max for c in cols)
    last_valid = min(prices[c].last_valid_index() or pd.Timestamp.min for c in cols)
    if first_valid >= last_valid:
        st.error("❌ 선택한 기간의 거래일 데이터가 부족합니다 (최소 2일 이상 필요).")
        return None
    prices = prices.loc[first_valid:last_valid].dropna()
    if len(prices) < 2:
        st.error("❌ 분석에 필요한 유효 거래일 데이터가 2일 미만입니다. 기간을 조금 더 넓혀주세요.")
        return None

    # 은대: 실제 경과 달력일로 일할 (② 252 가정 제거)
    if "BANK_DEPOSIT" in pt:
        elapsed = (prices.index - prices.index[0]).days.to_numpy(dtype="float64")
        prices["BANK_DEPOSIT"] = 100.0 * (1 + BANK_RATE) ** (elapsed / DAY_COUNT)

    idx = prices.index
    dt = pd.Series(np.diff(idx.values).astype("timedelta64[D]").astype("float64"),
                   index=idx[1:], name="dt_days")
    periods_per_year = calc_periods_per_year(idx)

    # ── 3. 환율 ──
    has_fx = not fx_df.empty
    if has_fx:
        fx_lvl = fx_df["close"].reindex(idx, method="ffill", tolerance=ASOF_TOLERANCE).ffill().bfill()
        fx_ret = fx_lvl.pct_change().iloc[1:].fillna(0.0)
    else:
        st.warning("⚠️ USD/KRW 환율을 불러오지 못해 환율 변동을 0으로 처리합니다.")
        fx_ret = pd.Series(0.0, index=idx[1:])

    # ── 4. 헤지 carry (④) ──
    has_us = any(t in us_set for t in pt)
    if has_us:
        kr_rate, us_rate, rate_note = get_rate_series(
            idx, params["hedge_cost_mode"], params["manual_kr_rate"], params["manual_us_rate"],
        )
        # 구간 (t-1, t] 의 carry는 t-1 시점 금리 적용
        diff_prev = ((kr_rate - us_rate) / 100.0).shift(1).iloc[1:]
        carry = diff_prev * dt / DAY_COUNT
        avg_carry_pa = float(((kr_rate - us_rate)).mean())
    else:
        carry = pd.Series(0.0, index=idx[1:])
        rate_note, avg_carry_pa = "해당 없음 (달러 자산 없음)", 0.0

    # ── 5. 일별 총수익률 (현지통화) ──
    returns = prices.pct_change().iloc[1:]
    n_days = len(returns)
    R = returns[pt].to_numpy(dtype="float64")
    fx_col = fx_ret.reindex(returns.index).fillna(0.0).to_numpy(dtype="float64")[:, None]
    car_col = carry.reindex(returns.index).fillna(0.0).to_numpy(dtype="float64")[:, None]

    is_us = np.array([t in us_set for t in pt])
    is_krfx = np.array([t in KR_LISTED_US_FX for t in pt])

    def decompose(h: float):
        """
        원화 수익률 = 현지수익률 + 환효과 + 헤지carry
        - 미국 상장(헤지비율 h): (1+r)(1+fx) − 1 − h·(fx − carry)
              → 현지 r / 환효과 (1−h)·fx + r·fx / carry h·carry
        - 국내상장 환노출 ETF: 현지 = (1+r)/(1+fx) − 1, 환효과 = r − 현지
        """
        local = R.copy()
        fxp = np.zeros_like(R)
        cp = np.zeros_like(R)
        if is_us.any():
            r_us = R[:, is_us]
            fxp[:, is_us] = (1 - h) * fx_col + r_us * fx_col
            cp[:, is_us] = h * car_col
        if is_krfx.any():
            r_kf = R[:, is_krfx]
            loc = (1 + r_kf) / (1 + fx_col) - 1
            local[:, is_krfx] = loc
            fxp[:, is_krfx] = r_kf - loc
        return local, fxp, cp

    # ── 6. 비중 산출 ──
    weights, cat_weights = _calc_weights(params, pt)
    if not weights:
        st.error("❌ 유효 비중을 산출할 수 없습니다.")
        return None
    weight_vec = np.array([weights.get(t, 0.0) for t in pt], dtype="float64")

    # ── 7. TAA 시그널 (① 시차 보정) ──
    taa_signal = pd.Series(0.0, index=returns.index)
    taa_days_rsi = 0
    if params["rsi_taa_enabled"]:
        if "SPY" in tr:
            # 전체 이력에서 시작일 120일 전부터 사용 (RSI 워밍업)
            spy_tr = tr["SPY"].loc[first_valid - pd.Timedelta(days=120):end_ts]
            spy_rsi = calc_rsi(spy_tr, params["rsi_period"])      # 미국 영업일 그대로 계산
            sig_native = compute_rsi_signal(
                spy_rsi, params["rsi_entry"], params["rsi_exit"], params["rsi_max_days"]
            )
            taa_signal = align_signal_no_lookahead(
                sig_native, idx, native_is_us=True, calendar_is_kr=calendar_is_kr,
            ).reindex(returns.index).fillna(0.0)
            taa_days_rsi = int((taa_signal > 0).sum())
        else:
            st.warning("⚠️ SPY 데이터를 불러오지 못해 RSI TAA를 적용하지 않았습니다.")

    if params["turnaround_enabled"] and params["turnaround_years"]:
        t_mask = returns.index.year.isin(params["turnaround_years"])
        taa_signal = ((taa_signal > 0) | t_mask).astype("float64")

    # ── 8. TAA 동적 비중 반영 ──
    weight_matrix = np.tile(weight_vec, (n_days, 1))
    eq_idx = [i for i, t in enumerate(pt) if group.get(t) == "equity"]
    bd_idx = [i for i, t in enumerate(pt) if group.get(t) == "bond"]
    alt_idx = [i for i, t in enumerate(pt) if group.get(t) == "alt"]

    base_eq_w = weight_vec[eq_idx].sum() if eq_idx else 0.0
    base_bd_w = weight_vec[bd_idx].sum() if bd_idx else 0.0
    target_eq = 0.30

    taa_mask = taa_signal.to_numpy() > 0
    if taa_mask.any() and base_eq_w > 0 and base_bd_w > 0 and target_eq > base_eq_w:
        eq_scale = target_eq / base_eq_w
        reduce   = target_eq - base_eq_w
        bd_scale = max(0.0, (base_bd_w - reduce) / base_bd_w)
        for i in eq_idx:
            weight_matrix[taa_mask, i] = weight_vec[i] * eq_scale
        for i in bd_idx:
            weight_matrix[taa_mask, i] = weight_vec[i] * bd_scale

    # ── 9. 포트폴리오 일별 수익률 ──
    # 공모주 Alpha: 실제 경과 달력일로 일할 (②)
    dt_arr = dt.reindex(returns.index).to_numpy(dtype="float64")
    alpha_arr = (1 + params["ipo_alpha"] / 100.0) ** (dt_arr / DAY_COUNT) - 1

    h_user = params["hedge_ratio"] / 100.0
    local_u, fx_u, car_u = decompose(h_user)
    port_open_arr = (weight_matrix * (local_u + fx_u + car_u)).sum(axis=1) + alpha_arr

    local_h, fx_h, car_h = decompose(1.0)
    port_hedged_arr = (weight_matrix * (local_h + fx_h + car_h)).sum(axis=1) + alpha_arr

    port_open = pd.Series(port_open_arr, index=returns.index, dtype="float64")
    port_hedged = pd.Series(port_hedged_arr, index=returns.index, dtype="float64")

    # 벤치마크: SPY 총수익 원화 환산 (환오픈)
    if "SPY" in returns.columns:
        bench_open = (1 + returns["SPY"]) * (1 + fx_ret.reindex(returns.index).fillna(0.0)) - 1
    else:
        bench_open = pd.Series(0.0, index=returns.index)

    # ── 10. NAV (기준일 = 100 포함) ──
    def to_nav(daily: pd.Series) -> pd.Series:
        nav = (1 + daily).cumprod() * 100.0
        return pd.concat([pd.Series([100.0], index=[idx[0]]), nav])

    nav_open = to_nav(port_open)
    nav_hedged = to_nav(port_hedged)
    nav_bench = to_nav(bench_open)

    # ── 11. KPI ──
    metric_open, ann_open, is_short = calc_returns_and_cagr(nav_open)
    _, ann_hedged, _ = calc_returns_and_cagr(nav_hedged)
    mdd_val    = calc_mdd(nav_open)
    vol_val    = calc_volatility(port_open, periods_per_year)
    sharpe_val = calc_sharpe(port_open, dt, periods_per_year)

    cumul   = (float(nav_open.iloc[-1])  / 100.0 - 1) * 100
    b_cumul = (float(nav_bench.iloc[-1]) / 100.0 - 1) * 100

    # ── 12. ⑤ 성과 기여도 분해 (NAV 가중 linking → 합계 = 총수익률) ──
    growth = np.r_[1.0, np.cumprod(1 + port_open_arr)[:-1]]     # NAV_{t-1}/NAV_0

    def linked(daily_component: np.ndarray) -> float:
        return float((daily_component * growth).sum())

    def bucket_local(cols_idx: list[int]) -> np.ndarray:
        if not cols_idx:
            return np.zeros(n_days)
        return (weight_matrix[:, cols_idx] * local_u[:, cols_idx]).sum(axis=1)

    cum_parts = {
        "bond_contrib":  linked(bucket_local(bd_idx)),
        "eq_contrib":    linked(bucket_local(eq_idx)),
        "alt_contrib":   linked(bucket_local(alt_idx)),
        "fx_contrib":    linked((weight_matrix * fx_u).sum(axis=1)),
        "carry_contrib": linked((weight_matrix * car_u).sum(axis=1)),
        "ipo_contrib":   linked(alpha_arr),
    }
    cum_total = float(nav_open.iloc[-1]) / 100.0 - 1          # == sum(cum_parts)

    if is_short:
        scale = 100.0                                            # 기간 누적 (%)
        total_display = cumul
    else:
        years = (nav_open.index[-1] - nav_open.index[0]).days / 365.25
        ann_total = ann_open / 100.0
        # 누적 기여도를 CAGR에 비례 배분 (합계 = CAGR 정확히 일치)
        scale = (ann_total / cum_total * 100.0) if abs(cum_total) > 1e-12 else (100.0 / years)
        total_display = ann_open

    attribution = {k: v * scale for k, v in cum_parts.items()}
    attribution["total_cagr"] = total_display
    attribution["check_gap"] = total_display - sum(v for k, v in attribution.items()
                                                   if k.endswith("_contrib"))

    return {
        "nav_open":             nav_open,
        "nav_hedged":           nav_hedged,
        "nav_benchmark":        nav_bench,
        "daily_returns":        port_open,
        "dt_days":              dt,
        "periods_per_year":     periods_per_year,
        "cagr":                 ann_open,
        "metric_display":       metric_open,
        "is_short_term":        is_short,
        "cagr_hedged":          ann_hedged,
        "mdd":                  mdd_val,
        "volatility":           vol_val,
        "sharpe":               sharpe_val,
        "fx_contribution":      attribution["fx_contrib"],
        "cumulative_return":    cumul,
        "benchmark_cumulative": b_cumul,
        "yearly_portfolio":     calc_yearly_returns(nav_open),
        "yearly_benchmark":     calc_yearly_returns(nav_bench),
        "yearly_hedged":        calc_yearly_returns(nav_hedged),
        "drawdown":             calc_drawdown_series(nav_open),
        "weights":              weights,
        "category_weights":     cat_weights,
        "attribution":          attribution,
        "analysis_start":       idx[0],
        "analysis_end":         idx[-1],
        "total_days":           (idx[-1] - idx[0]).days,
        "trading_days":         n_days,
        "calendar_label":       calendar_label,
        "rate_note":            rate_note,
        "avg_carry_pa":         avg_carry_pa,
        "hedge_ratio":          params["hedge_ratio"],
        "taa_days_rsi":         taa_days_rsi,
        "start_adjustment":     start_adjustment,
        "requested_start":      start_req.date(),
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

        # ── 1. 분석 기간 (전체 구간 선택 가능, 실행 시 가장 늦게 상장한 종목 기준으로 시작일 보정) ──
        with st.expander("📅 분석 기간 설정", expanded=True):
            today = date.today()
            ss = st.session_state

            # 최초 진입(또는 로그아웃 후) 기본값: 전체 기간
            if ss.get("period_preset") not in PERIOD_PRESETS:
                ss["period_preset"] = PRESET_ALL
            if "period_start" not in ss or "period_end" not in ss:
                init = preset_date_range(ss["period_preset"], today) or (DATA_FLOOR, today)
                ss["period_start"], ss["period_end"] = init

            # 직전 실행에서 보정된 조회 시작일을 위젯 생성 전에 반영
            if "_pending_period_start" in ss:
                ss["period_start"] = ss.pop("_pending_period_start")

            # 유효성 검증: 선택 가능 범위 [DATA_FLOOR, 오늘] 안으로 보정
            ss["period_start"] = clamp_period_date(ss["period_start"], today)
            ss["period_end"] = clamp_period_date(ss["period_end"], today)

            def _on_preset_change():
                rng = preset_date_range(st.session_state["period_preset"], date.today())
                if rng is not None:          # '사용자 직접 지정'이면 현재 날짜 유지
                    st.session_state["period_start"], st.session_state["period_end"] = rng

            def _on_date_change():
                # 날짜를 직접 바꾸면 프리셋 표시를 '사용자 직접 지정'으로 전환
                st.session_state["period_preset"] = PRESET_CUSTOM

            preset = st.selectbox(
                "⚡ 간편 기간 프리셋", PERIOD_PRESETS,
                key="period_preset", on_change=_on_preset_change,
            )

            col_d1, col_d2 = st.columns(2)
            with col_d1:
                shown_start = st.date_input(
                    "시작일",
                    min_value=DATA_FLOOR,
                    max_value=today,
                    key="period_start",
                    on_change=_on_date_change,
                )
            with col_d2:
                end_date = st.date_input(
                    "종료일",
                    min_value=DATA_FLOOR,
                    max_value=today,
                    key="period_end",
                    on_change=_on_date_change,
                )
            st.caption(
                "※ 실제 조회 시작일은 선택한 종목 중 **가장 늦게 상장한 종목의 상장일**로 자동 보정됩니다. "
                "보정되면 시작일 칸이 바뀌고 안내 팝업이 뜹니다."
            )

            # 프리셋을 쓰는 동안에는 '프리셋이 뜻하는 시작일'로 요청한다.
            # (예: 전체 기간 → 종목을 바꾸면 그 조합의 가장 이른 공통 시작일로 다시 계산됨)
            preset_rng = preset_date_range(preset, today)
            start_date = preset_rng[0] if preset_rng is not None else shown_start

            if shown_start >= end_date:
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
            st.caption("비중 0%인 자산군의 종목은 공통 구간 계산에서 제외됩니다.")

        # ── 5. 공모주 수익 기여도(Alpha) ──
        with st.expander("💰 공모주 수익 기여도 (Alpha)", expanded=False):
            ipo_alpha = st.slider(
                "공모주 연간 Alpha 가산 (%p)", 0.0, 1.0, 0.0, 0.05,
                help="실제 경과 달력일 기준으로 일할 가산됩니다. (목표 모델: 0~1%대)"
            )

        # ── 6. 동적 TAA (전술적 자산배분) ──
        with st.expander("🔄 동적 TAA (전술적 자산배분) 토글", expanded=False):
            st.caption("**[전략 1] 기술적 지표 14일 RSI 과매도 탄력 운용**")
            st.caption("신호는 SPY 종가 확인 후 **다음 영업일 수익률부터** 적용됩니다 (미래 정보 미사용).")
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
                st.caption("⚠️ 연도를 사후에 고르는 방식이라 결과에 hindsight bias가 포함됩니다.")
                yr_range = list(range(DATA_FLOOR.year, date.today().year + 1))
                ta_years = st.multiselect("적극 투자 국면 연도 선택", yr_range, default=[])

        # ── 7. 환율 및 통화 비교 제어 ──
        with st.expander("💱 환율 및 통화 비교 제어", expanded=True):
            st.caption("기본값: **환오픈 (USD 노출)** - 연평균 3% 이상 원화 약세/달러 강세 기대 반영")
            hedge_ratio = st.slider(
                "환헤지 비중 (%)", 0, 100, 0, 5,
                help="0% = 100% 환오픈 (기본값), 100% = 완전 환헤지"
            )
            show_hedged = st.checkbox("환헤지(USD) 수익률 비교 라인 표시", value=True)

            st.markdown("**헤지 비용(금리차) 산출**")
            hedge_cost_mode = st.radio(
                "헤지 비용 산출 방식", ["자동", "수동"], horizontal=True,
                label_visibility="collapsed",
                help="헤지 손익 ≈ (원화 단기금리 − 달러 단기금리) × 기간. 원화 금리가 낮으면 비용(−).",
            )
            c_r1, c_r2 = st.columns(2)
            with c_r1:
                manual_kr_rate = st.number_input("원화 단기금리 (연 %)", 0.0, 15.0, 2.50, 0.05, format="%.2f")
            with c_r2:
                manual_us_rate = st.number_input("달러 단기금리 (연 %)", 0.0, 15.0, 4.00, 0.05, format="%.2f")
            st.caption(
                "자동: 달러 ^IRX(미 T-bill 3M), 원화 FRED 한국 3M 금리(월별). "
                "조회 실패 시 위 수동값을 사용합니다. 수동값은 현재 시장금리로 확인 후 입력하세요."
            )

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
        "hedge_cost_mode":  hedge_cost_mode,
        "manual_kr_rate":   manual_kr_rate,
        "manual_us_rate":   manual_us_rate,
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
    _adj = res.get("start_adjustment")
    # 분석 시작일이 상장일 보정으로 정해졌으면 첫 해를 '상장 이후'로 표기
    start_is_listing = bool(_adj) and abs((res["analysis_start"] - pd.Timestamp(_adj["new_start"])).days) <= PARTIAL_YEAR_GRACE_DAYS
    total_days = res.get("total_days", 0)
    ppy = res.get("periods_per_year", 252.0)

    st.caption(
        f"분석 데이터 구간: **{p_start} ~ {p_end}** ({total_days}일, {trading_days}영업일) | "
        f"기준 캘린더: **{res.get('calendar_label', '-')}** (연 {ppy:.0f}회 관측) | 통화 기준: **KRW (원화)**"
    )

    adj = res.get("start_adjustment")
    if adj:
        st.caption(f"📅 {adj['message']} (요청 시작일 {adj['requested']:%Y-%m-%d} → {adj['new_start']:%Y-%m-%d})")

    if is_short:
        st.markdown(
            f"""
            <div class="short-banner">
            ⚡ <b>단기 모니터링 모드 활성화</b>: 조회 기간이 1년 미만({trading_days}영업일)입니다.
            기간 단순 누적 수익률을 중심으로 분석하며, 연환산(참고치)이 함께 병기됩니다.
            기여도 분해도 모두 <b>기간 누적 기준(%p)</b>으로 표시됩니다.
            </div>
            """,
            unsafe_allow_html=True,
        )

    attr = res["attribution"]

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
        label_fx = "환차익 기여도 (연)" if not is_short else "환차익 기여 (기간)"
        st.metric(
            label_fx, f"{res['fx_contribution']:+.2f}%p",
            delta=f"헤지 손익 {attr['carry_contrib']:+.2f}%p", delta_color="off",
        )
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
    unit_txt = "기간 누적 기준" if is_short else "연환산(CAGR) 기준"
    st.markdown(
        f"""
        자산운용 펀드 상품 기획 시 설계된 **4대 핵심 기대수익 구조**와 실제 백테스팅 기간 동안의 **실현 기여도**를 비교합니다.
        모든 항목은 **{unit_txt}**이며, 일별 기여도를 직전 NAV로 연결(linking)해 **항목 합계가 총수익률과 정확히 일치**합니다.
        """
    )

    a1, a2, a3, a4 = st.columns(4)
    with a1:
        st.metric("① 국채 ETF 기여도", f"{attr['bond_contrib']:+.2f}%p",
                  help="채권 ETF의 현지통화 총수익(이자+가격) 기여. 환효과는 ③에 별도 집계")
        st.caption("📌 **목표 모델**: 3.0~4.0%p")
    with a2:
        st.metric("② 지수 ETF 기여도", f"{attr['eq_contrib']:+.2f}%p",
                  help="지수 ETF의 현지통화 총수익 기여 (국내상장 미국지수 ETF는 환효과를 분리)")
        st.caption("📌 **목표 모델**: 0.0~3.0%p")
    with a3:
        st.metric("③ 환차익 기여도", f"{attr['fx_contrib']:+.2f}%p",
                  help="USD/KRW 변동에 따른 환산 손익 (환오픈 부분 + 수익분의 환노출)")
        st.caption("📌 **목표 모델**: 3.0~5.0%p")
    with a4:
        st.metric("④ 공모주 Alpha", f"{attr['ipo_contrib']:+.2f}%p", help="연 0~1%p 가정치 (달력일 일할)")
        st.caption("📌 **목표 모델**: 0.0~1.0%p")

    b1, b2, b3 = st.columns(3)
    with b1:
        st.metric("⑤ 금·현금성 기여도", f"{attr['alt_contrib']:+.2f}%p", help="GLDM, 단기채권 ETF, 은대")
    with b2:
        st.metric(
            "⑥ 환헤지 손익 (금리차)", f"{attr['carry_contrib']:+.2f}%p",
            help=f"헤지비율 {res.get('hedge_ratio', 0)}% × (원화 − 달러 단기금리). "
                 f"기간 평균 금리차 {res.get('avg_carry_pa', 0):+.2f}%p/년",
        )
    with b3:
        label_total = "합산 실현 수익률" if is_short else "합산 실현 CAGR"
        st.metric(label_total, f"{attr['total_cagr']:.2f}%", delta=f"{attr['total_cagr'] - 8.0:+.2f}%p vs 8.0% 목표")
        st.caption("🏆 **목표 종합**: **8.0% ~ 10.0%대**")

    labels = ["① 국채 ETF", "② 지수 ETF", "③ 환차익(USD/KRW)", "④ 공모주 Alpha",
              "⑤ 금·현금성", "⑥ 환헤지 손익", "합산 실현치"]
    values = [attr['bond_contrib'], attr['eq_contrib'], attr['fx_contrib'], attr['ipo_contrib'],
              attr['alt_contrib'], attr['carry_contrib'], attr['total_cagr']]
    fig_attr = go.Figure(go.Bar(
        x=labels, y=values,
        marker=dict(color=["#1976D2", "#388E3C", "#F57C00", "#7B1FA2", "#8D6E63", "#00838F", "#D32F2F"]),
        text=[f"{v:+.2f}%p" if i < 6 else f"{v:.2f}%" for i, v in enumerate(values)],
        textposition="outside",
    ))
    fig_attr.add_hline(y=8.0, line_dash="dash", line_color="#E53935", annotation_text="목표 수익률 8.0%")
    fig_attr.update_layout(
        title=f"원천별 수익 기여도 분해 (%p, {unit_txt})",
        template="plotly_white",
        yaxis_title="수익 기여도 (%p)",
        height=340,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    st.plotly_chart(fig_attr, use_container_width=True)
    st.caption(f"헤지 금리 출처: {res.get('rate_note', '-')}")

    st.divider()

    # ────────────────────────────────────────────────────────────────
    # [3] 시각화 차트 1 & 2
    # ────────────────────────────────────────────────────────────────
    st.subheader("📈 Chart 1 — 누적 자산가치(NAV) 추이")
    fig_nav = go.Figure()
    fig_nav.add_trace(go.Scatter(
        x=res["nav_open"].index, y=res["nav_open"].values,
        name=f"혼합형 펀드 (환헤지 {res.get('hedge_ratio', 0)}%)",
        line=dict(color="#1565C0", width=2.5),
    ))
    if show_hedged:
        fig_nav.add_trace(go.Scatter(
            x=res["nav_hedged"].index, y=res["nav_hedged"].values,
            name="혼합형 펀드 (환헤지 100%, 헤지비용 반영)",
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
        dt_days = res.get("dt_days")
        cagr_label = "연평균 복리수익률 (CAGR)" if not is_short else "기간 누적수익률 (연환산)"
        summary = pd.DataFrame({
            "지표": ["누적 수익률", cagr_label, "연환산 변동성", "샤프 지수 (Rf=3%)", "최대 낙폭 (MDD)"],
            "혼합형 펀드": [
                f"{res['cumulative_return']:.2f}%",
                f"{res['cagr']:.2f}%",
                f"{res['volatility']:.2f}%",
                f"{res['sharpe']:.2f}",
                f"{res['mdd']:.2f}%",
            ],
            "S&P500 벤치마크(KRW)": [
                f"{res['benchmark_cumulative']:.2f}%",
                f"{calc_returns_and_cagr(res['nav_benchmark'])[1]:.2f}%",
                f"{calc_volatility(bench_ret, ppy):.2f}%",
                f"{calc_sharpe(bench_ret, dt_days, ppy):.2f}",
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
            yearly["환헤지 100%"] = res["yearly_hedged"].round(2)
        y_labels, y_notes = yearly_labels(yearly.index, res["analysis_start"], res["analysis_end"],
                                          start_is_listing=start_is_listing)
        yearly.index = pd.Index(y_labels, name="연도")
        st.dataframe(yearly, use_container_width=True)
        for note in y_notes:
            if note:
                st.caption(note.replace("*", "\\*", 1))

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
        "NAV_펀드":     res["nav_open"].values.round(4),
        "NAV_환헤지100": res["nav_hedged"].values.round(4),
        "NAV_벤치마크": res["nav_benchmark"].values.round(4),
    })
    yp = res["yearly_portfolio"]
    yb = res["yearly_benchmark"].reindex(yp.index)
    exp_labels, exp_notes = yearly_labels(yp.index, res["analysis_start"], res["analysis_end"],
                                          start_is_listing=start_is_listing)
    yearly_exp = pd.DataFrame({
        "연도":            exp_labels,
        "혼합형펀드(%)":    yp.values.round(2),
        "S&P500(KRW)(%)": yb.values.round(2),
        "비고":            exp_notes,
    })
    attr_df = pd.DataFrame({
        "구분": labels,
        "설계 목표 모델": ["3.0 ~ 4.0%대", "0.0 ~ 3.0%대", "3.0 ~ 5.0%대", "0.0 ~ 1.0%대", "-", "-", "8.0 ~ 10.0%대"],
        f"백테스팅 실현 기여도(%p, {unit_txt})": [round(v, 2) for v in values],
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

    popup_msg = st.session_state.pop("_start_adjust_popup", None)
    if popup_msg:
        show_start_adjust_popup(popup_msg)

    if run_clicked:
        if params["start_date"] >= params["end_date"]:
            st.error("❌ 시작일은 종료일보다 이전이어야 합니다. 사이드바에서 기간을 다시 선택하세요.")
            return
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

            # 실제 적용된 조회 시작일을 사이드바 시작일 칸에 반영 (위젯 생성 전에 넣어야 하므로 rerun)
            adj = results.get("start_adjustment")
            effective_start = adj["new_start"] if adj else results["requested_start"]
            if effective_start != st.session_state.get("period_start"):
                st.session_state["_pending_period_start"] = effective_start
                if adj:
                    st.session_state["_start_adjust_popup"] = adj["message"]
                st.rerun()

    if "results" in st.session_state:
        render_dashboard(
            st.session_state["results"],
            st.session_state.get("show_hedged", True),
        )
    else:
        st.markdown("## 🏛️ 국채·지수 ETF 혼합형 펀드 퀀트 백테스팅 대시보드")
        st.info("👈 좌측 사이드바에서 **분석 기간(기본: 전체 기간 — 선택 종목 중 가장 늦게 상장한 종목의 상장일부터) 및 ETF 비중**을 설정하고 **🚀 시뮬레이션 재실행** 버튼을 누르세요.")
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