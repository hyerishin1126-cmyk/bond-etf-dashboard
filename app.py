"""
국채·지수 ETF 혼합형 펀드 백테스팅 대시보드
=====================================================
- 투자대상:
    1) 미국 국채 ETF: 미국 상장(SGOV, SHY, IEI, IEF, TLT) + 국내상장 환노출(0046A0, 329750, 308620, 0085P0, 476760)
       + 국내상장 환헤지(H)(0091C0, 453850, 484790)
    2) 한국 국고채 ETF (KODEX 국고채3년, 국고채10년액티브, 국고채30년액티브)
    3) 미국 지수 ETF: 미국 상장(VOO, QQQM) + 국내상장 환노출(379800, 360750, 379810, 133690)
    4) 한국 지수 ETF (TIGER 200)
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
import json
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
    "SGOV":      "iShares 0-3M Treasury Bond",
    "0046A0.KS": "TIGER 미국초단기(3개월이하)국채",
    "329750.KS": "TIGER 미국달러단기채권액티브",
    "SHY":       "iShares 1-3Y Treasury Bond",
    "IEI":       "iShares 3-7Y Treasury Bond",
    "IEF":       "iShares 7-10Y Treasury Bond",
    "308620.KS": "KODEX 미국10년국채선물",
    "0085P0.KS": "ACE 미국10년국채액티브",
    "0091C0.KS": "KODEX 미국10년국채액티브(H)",
    "TLT":       "iShares 20+Y Treasury Bond",
    "476760.KS": "ACE 미국30년국채액티브",
    "453850.KS": "ACE 미국30년국채액티브(H)",
    "484790.KS": "KODEX 미국30년국채액티브(H)",
}

KR_BOND = {
    "114260.KS": "KODEX 국고채3년",
    "471230.KS": "KODEX 국고채10년액티브",
    "439870.KS": "KODEX 국고채30년액티브",
}

# 공식 상장일 (종목명 옆 표시, 조회 시작일 보정·팝업 안내에 사용).
# 2026-11-12 검증: 한국 종목은 거래소 '상장일' 기준(설정일 아님), 미국 종목은 운용사 Inception Date.
# 여기에 없는 종목은 시세 데이터의 첫 거래일을 상장일로 간주한다.
LISTING_DATES: dict[str, date] = {
    # 미국 국채 ETF
    "SGOV":      date(2020, 5, 26),    # iShares 0-3 Month Treasury Bond ETF
    "0046A0.KS": date(2025, 4, 29),    # TIGER 미국초단기(3개월이하)국채
    "329750.KS": date(2019, 7, 24),    # TIGER 미국달러단기채권액티브
    "SHY":       date(2002, 7, 22),    # iShares 1-3 Year Treasury Bond ETF
    "IEI":       date(2007, 1, 5),     # iShares 3-7 Year Treasury Bond ETF
    "IEF":       date(2002, 7, 22),    # iShares 7-10 Year Treasury Bond ETF
    "308620.KS": date(2018, 10, 19),   # KODEX 미국10년국채선물
    "0085P0.KS": date(2025, 7, 22),    # ACE 미국10년국채액티브
    "0091C0.KS": date(2025, 8, 19),    # KODEX 미국10년국채액티브(H)
    "TLT":       date(2002, 7, 22),    # iShares 20+ Year Treasury Bond ETF
    "476760.KS": date(2024, 3, 12),    # ACE 미국30년국채액티브
    "453850.KS": date(2023, 3, 14),    # ACE 미국30년국채액티브(H)
    "484790.KS": date(2024, 6, 18),    # KODEX 미국30년국채액티브(H)
    # 한국 국고채 ETF
    "114260.KS": date(2009, 7, 29),    # KODEX 국고채3년
    "471230.KS": date(2023, 11, 14),   # KODEX 국고채10년액티브
    "439870.KS": date(2022, 8, 23),    # KODEX 국고채30년액티브
    # 미국 지수 ETF
    "VOO":       date(2010, 9, 7),     # Vanguard S&P 500 ETF
    "379800.KS": date(2021, 4, 9),     # KODEX 미국S&P500
    "360750.KS": date(2020, 8, 7),     # TIGER 미국S&P500
    "QQQM":      date(2020, 10, 13),   # Invesco NASDAQ 100 ETF
    "379810.KS": date(2021, 4, 9),     # KODEX 미국나스닥100
    "133690.KS": date(2010, 10, 18),   # TIGER 미국나스닥100
    # 한국 지수 ETF
    "102110.KS": date(2008, 4, 3),     # TIGER 200
    # 대체·현금성, 벤치마크
    "GLDM":      date(2018, 6, 25),    # SPDR Gold MiniShares Trust
    "153130.KS": date(2012, 2, 22),    # KODEX 단기채권
    "SPY":       date(1993, 1, 22),    # SPDR S&P 500 ETF Trust (벤치마크·RSI 신호)
}


def listing_tag(t: str) -> str:
    """종목명 옆에 붙이는 ' (상장 yyyy-mm-dd)' 표기. 상장일이 등록되지 않은 종목(은대 등)은 빈 문자열."""
    return f" (상장 {LISTING_DATES[t]:%Y-%m-%d})" if t in LISTING_DATES else ""


US_EQUITY = {
    "VOO":       "Vanguard S&P 500",
    "379800.KS": "KODEX 미국S&P500",
    "360750.KS": "TIGER 미국S&P500",
    "QQQM":      "Invesco NASDAQ 100",
    "379810.KS": "KODEX 미국나스닥100",
    "133690.KS": "TIGER 미국나스닥100",
}

KR_EQUITY = {
    "102110.KS": "TIGER 200",
}

CASH_OPTS = {
    "153130.KS":    "KODEX 단기채권",
    "BANK_DEPOSIT": "은대 (고정 연 2.53% 일할)",
}

# 국내상장이지만 기초자산이 달러 자산이라 원화 가격에 환율 효과가 섞여 있는 ETF
KR_LISTED_US_FX = {
    "0046A0.KS", "329750.KS", "308620.KS", "0085P0.KS", "476760.KS",   # 미국 국채 (환노출)
    "379800.KS", "360750.KS", "379810.KS", "133690.KS",        # 미국 지수 (환노출)
}
# 국내상장 환헤지형(H): 상품 안에서 이미 헤지되어 원화 가격에 환율 효과가 없음 (헤지 비용은 가격에 반영)
KR_LISTED_HEDGED = {"0091C0.KS", "453850.KS", "484790.KS"}


def is_usd_listed(t: str) -> bool:
    """미국 상장(달러 표시) 종목 여부. 환헤지 슬라이더는 이 종목에만 적용된다."""
    return t != "BANK_DEPOSIT" and not (t.endswith(".KS") or t.endswith(".KQ"))


def fx_type_label(t: str) -> str:
    if t in KR_LISTED_HEDGED:
        return "국내상장 환헤지(H)"
    if t in KR_LISTED_US_FX:
        return "국내상장 환노출"
    if is_usd_listed(t):
        return "미국 상장(달러)"
    return "원화 자산"

ALL_NAMES = {**US_BOND, **KR_BOND, **US_EQUITY, **KR_EQUITY, **CASH_OPTS,
             "GLDM": "SPDR Gold MiniShares", "SPY": "SPDR S&P 500 Trust"}

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


def fetch_auto_rates(end: str) -> dict[str, tuple[pd.Series, str, str]]:
    """
    자동 금리 원자료 조회. 반환: {"KRW"/"USD": (연 % 시계열, 출처, 자료 주기)}
    - USD: ^IRX(미 T-bill 13주, 일별) → 실패 시 FRED DTB3(일별)
    - KRW: FRED IR3TIB01KRM156N (한국 3개월 금리, 월평균 · 날짜는 해당 월 1일로 표기)
    """
    out: dict[str, tuple[pd.Series, str, str]] = {}
    irx = fetch_raw("^IRX", DATA_FLOOR.strftime("%Y-%m-%d"), end)
    if not irx.empty:
        out["USD"] = (irx["close"].sort_index(), "^IRX (미 T-bill 13주)", "일별")
    else:
        fr = fetch_fred_series(FRED_USD_3M)
        if not fr.empty:
            out["USD"] = (fr, f"FRED {FRED_USD_3M} (미 T-bill 3개월)", "일별")
    k = fetch_fred_series(FRED_KRW_3M)
    if not k.empty:
        out["KRW"] = (k, f"FRED {FRED_KRW_3M} (한국 3개월 금리)", "월평균")
    return out


def get_rate_series(index: pd.DatetimeIndex, mode: str, manual_kr: float,
                    manual_us: float) -> tuple[pd.Series, pd.Series, str, dict]:
    """
    원화·달러 단기금리(연 %)를 index 위에 as-of 정렬. 자동 조회 실패 시 수동값.
    반환: (원화 금리, 달러 금리, 출처 요약 문자열, 상세 정보 dict)
    """
    auto = fetch_auto_rates(index[-1].strftime("%Y-%m-%d")) if mode == "자동" else {}
    series: dict[str, pd.Series] = {}
    info: dict[str, dict] = {}
    manual_vals = {"KRW": manual_kr, "USD": manual_us}

    for ccy in ("KRW", "USD"):
        if ccy in auto:
            raw_s, src, freq = auto[ccy]
            used = raw_s[raw_s.index <= index[-1]]        # 분석 종료일까지만 사용
            if used.empty:
                used = raw_s
            aligned = _asof(used, index)
            # 월평균 자료는 그 달 말일까지 유효한 값으로 보고 경과일 계산
            covered_to = used.index[-1] + pd.offsets.MonthEnd(0) if freq == "월평균" else used.index[-1]
            lag_days = max((index[-1] - covered_to).days, 0)
            info[ccy] = {
                "출처": src, "주기": freq, "수동값 사용": False,
                "원자료 최신 기준일": used.index[-1].date(),
                "원자료 최신값(%)": float(used.iloc[-1]),
                "최신값 경과일": lag_days,
            }
        else:
            aligned = pd.Series(manual_vals[ccy], index=index, dtype="float64")
            src = "수동 입력" + (" (자동 조회 실패)" if mode == "자동" else "")
            info[ccy] = {
                "출처": src, "주기": "고정", "수동값 사용": True,
                "원자료 최신 기준일": None, "원자료 최신값(%)": manual_vals[ccy], "최신값 경과일": 0,
            }
        info[ccy].update({
            "분석 시작일 값(%)": float(aligned.iloc[0]),
            "분석 종료일 값(%)": float(aligned.iloc[-1]),
            "기간 평균(%)": float(aligned.mean()),
            "기간 최저(%)": float(aligned.min()),
            "기간 최고(%)": float(aligned.max()),
        })
        series[ccy] = aligned

    parts = []
    for ccy, label in (("KRW", "원화"), ("USD", "달러")):
        d = info[ccy]
        if d["수동값 사용"]:
            parts.append(f"{label} {d['원자료 최신값(%)']:.2f}% ({d['출처']})")
        else:
            parts.append(f"{label} {d['원자료 최신값(%)']:.2f}% ({d['출처']}, {d['원자료 최신 기준일']:%Y-%m-%d} {d['주기']})")
    if mode == "자동" and any(info[c]["수동값 사용"] for c in info):
        parts.append("⚠️ 자동 조회 일부 실패 → 수동값 대체")
    return series["KRW"], series["USD"], " · ".join(parts), info


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
# 자산군 정의: (키, params 종목 목록 키, 표시명, 비중 슬라이더 키)
ASSET_CLASSES = [
    ("us_bond", "us_bonds",  "미국 국고채",   "weight_us_bond"),
    ("kr_bond", "kr_bonds",  "한국 국고채",   "weight_kr_bond"),
    ("us_eq",   "us_equity", "미국 지수 ETF", "weight_us_eq"),
    ("kr_eq",   "kr_equity", "한국 지수 ETF", "weight_kr_eq"),
]
CLASS_LABEL = {k: lbl for k, _, lbl, _ in ASSET_CLASSES} | {"alt": "대체·현금성"}


def ticker_class(params: dict, t: str) -> str:
    """종목이 속한 자산군 키 (us_bond / kr_bond / us_eq / kr_eq / alt)."""
    for k, lst, _, _ in ASSET_CLASSES:
        if t in params.get(lst, []):
            return k
    return "alt"


def class_split(params: dict, cls: str, tickers: list[str]) -> dict[str, float]:
    """
    자산군 내 종목별 비중 (합계 1.0). 0% 종목은 제외.
    params["splits"][cls] = {ticker: 입력 비중(%)} — 없으면 균등 배분.
    """
    raw = (params.get("splits") or {}).get(cls) or {}
    vals = {t: float(raw.get(t, 0.0)) if raw else 1.0 for t in tickers}
    vals = {t: v for t, v in vals.items() if v > 0}
    tot = sum(vals.values())
    return {t: v / tot for t, v in vals.items()} if tot > 0 else {}


def hedge_ratio_for(params: dict, t: str) -> float | None:
    """종목별 환헤지 비율(0~1). 미국 국고채·미국 지수 ETF만 헤지, 금(GLDM)은 환오픈, 원화 자산은 None."""
    legacy = params.get("hedge_ratio", 0)          # 구버전 단일 헤지 비율 호환
    if not is_usd_listed(t):
        return None                                # 국내상장 종목은 슬라이더 헤지 대상 아님
    if t in params.get("us_bonds", []):
        return params.get("hedge_us_bond", legacy) / 100.0
    if t in params.get("us_equity", []):
        return params.get("hedge_us_eq", legacy) / 100.0
    if t == "GLDM":
        return 0.0
    return None


def _calc_weights(params: dict, available: list[str]) -> tuple[dict[str, float], dict[str, float]]:
    """
    포트폴리오 종목별 비중.
    ① 자산군 비중(슬라이더)을 합계 100%로 정규화
    ② 자산군 안에서는 종목별 입력 비중(splits)으로 나눔 (입력 없으면 균등)
    ③ 미국 국고채가 비어 있으면 그 비중은 한국 국고채로 이전
    반환: (종목별 비중, 자산군별 실제 비중) — 자산군 비중은 최종 종목 비중을 다시 합산한 값
    """
    raw_w = {k: params[wk] / 100.0 for k, _, _, wk in ASSET_CLASSES}
    raw_w["alt"] = params["weight_alt_cash"] / 100.0
    sum_raw = sum(raw_w.values())
    if sum_raw <= 0:
        return {}, {}
    c = {k: v / sum_raw for k, v in raw_w.items()}

    weights: dict[str, float] = {}

    def put(cls: str, list_key: str) -> bool:
        lst = [t for t in params[list_key] if t in available]
        sp = class_split(params, cls, lst)
        for t, share in sp.items():
            weights[t] = weights.get(t, 0.0) + c[cls] * share
        return bool(sp)

    if not (c["us_bond"] > 0 and put("us_bond", "us_bonds")):
        c["kr_bond"] += c["us_bond"]          # 미국채 미선택 → 한국 국고채로 이전
        c["us_bond"] = 0.0
    if c["kr_bond"] > 0:
        put("kr_bond", "kr_bonds")
    if c["us_eq"] > 0:
        put("us_eq", "us_equity")
    if c["kr_eq"] > 0:
        put("kr_eq", "kr_equity")

    gold_on = params["gold_enabled"] and "GLDM" in available
    cash_tk = params["cash_ticker"]
    cash_ok = cash_tk and cash_tk in available
    if c["alt"] > 0:
        if gold_on and cash_ok:
            weights["GLDM"] = c["alt"] * 0.5
            weights[cash_tk] = c["alt"] * 0.5
        elif gold_on:
            weights["GLDM"] = c["alt"]
        elif cash_ok:
            weights[cash_tk] = c["alt"]

    tot = sum(weights.values())
    if tot > 0:
        weights = {k: v / tot for k, v in weights.items()}

    category_summary = {CLASS_LABEL[k]: 0.0 for k in ["us_bond", "kr_bond", "us_eq", "kr_eq", "alt"]}
    for t, w in weights.items():
        category_summary[CLASS_LABEL[ticker_class(params, t)]] += w
    return weights, category_summary


def weight_table(params: dict, weights: dict[str, float], with_hedge: bool = True) -> pd.DataFrame:
    """자산군·종목별 비중 표 (자산군 내 비중, 포트폴리오 비중, 환헤지 비율)."""
    order = {k: i for i, k in enumerate(["us_bond", "kr_bond", "us_eq", "kr_eq", "alt"])}
    cls_tot: dict[str, float] = {}
    for t, w in weights.items():
        k = ticker_class(params, t)
        cls_tot[k] = cls_tot.get(k, 0.0) + w
    rows = []
    for t, w in weights.items():
        k = ticker_class(params, t)
        row = {
            "자산군": CLASS_LABEL[k],
            "종목": t.replace(".KS", ""),
            "종목명": ALL_NAMES.get(t, t),
            "상장일": f"{LISTING_DATES[t]:%Y-%m-%d}" if t in LISTING_DATES else "-",
            "자산군 내 비중(%)": round(w / cls_tot[k] * 100, 2) if cls_tot[k] > 0 else 0.0,
            "포트폴리오 비중(%)": round(w * 100, 2),
            "_o": (order[k], -w),
        }
        if with_hedge:
            h = hedge_ratio_for(params, t)
            if h is not None:
                row["환헤지(%)"] = "환오픈" if t == "GLDM" else f"{h * 100:.0f}%"
            elif t in KR_LISTED_HEDGED:
                row["환헤지(%)"] = "상품 자체 헤지(H)"
            elif t in KR_LISTED_US_FX:
                row["환헤지(%)"] = "환노출(헤지 불가)"
            else:
                row["환헤지(%)"] = "-"
        rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("_o").drop(columns="_o").reset_index(drop=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BACKTEST ENGINE & ATTRIBUTION BREAKDOWN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def run_backtest(params: dict) -> dict | None:
    start_req = pd.Timestamp(params["start_date"])
    end_ts = pd.Timestamp(params["end_date"])
    e_str = end_ts.strftime("%Y-%m-%d")
    floor_str = DATA_FLOOR.strftime("%Y-%m-%d")     # 상장일 파악을 위해 항상 전체 이력 조회 (종목별 캐시)

    # ── 0. 편입 후보: 비중이 0보다 큰 종목만 (비중 0% 종목·자산군은 공통 구간을 줄이지 않도록 제외) ──
    candidates = list(dict.fromkeys(
        params["us_bonds"] + params["kr_bonds"] + params["us_equity"] + params["kr_equity"]
        + (["GLDM"] if params["gold_enabled"] else [])
        + ([params["cash_ticker"]] if params["cash_ticker"] else [])
    ))
    pre_w, _ = _calc_weights(params, candidates)
    bucket = {"us_bond": "bond", "kr_bond": "bond", "us_eq": "equity", "kr_eq": "equity", "alt": "alt"}
    group: dict[str, str] = {t: bucket[ticker_class(params, t)] for t, w in pre_w.items() if w > 0}
    if not group:
        st.error("❌ 비중이 0%보다 큰 자산군에서 최소 하나의 종목을 선택하세요.")
        return None

    us_set = {t for t in list(group) + ["GLDM"] if is_usd_listed(t)}     # 미국 상장(달러 표시) 종목
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
    #   상장일 = LISTING_DATES의 공식 상장일 (없으면 시세 데이터 첫 거래일).
    #   실제 분석 가능일 = max(상장일, 데이터 첫 거래일) — 시세 데이터가 상장일보다 늦게 시작하는 경우 대비.
    #   달러 자산이 있으면 USD/KRW 환율 데이터 시작일도 함께 고려.
    fx_df = fetch_raw("KRW=X", floor_str, e_str)
    listing_info: dict[str, tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]] = {}   # (상장일, 데이터 첫날, 분석 가능일)
    for t in avail_mkt:
        data_first = raw[t].index[0]
        listed = pd.Timestamp(LISTING_DATES[t]) if t in LISTING_DATES else data_first
        listing_info[t] = (listed, data_first, max(listed, data_first))
    if any(t in us_set or t in KR_LISTED_US_FX for t in avail_mkt) and not fx_df.empty:
        fx_first = fx_df.index[0]
        listing_info["KRW=X"] = (fx_first, fx_first, fx_first)

    start_ts = start_req
    start_adjustment = None
    if listing_info:
        latest = max(v[2] for v in listing_info.values())
        if latest > start_req:
            causes = [t for t, v in listing_info.items() if v[2] == latest]
            stock_causes = [t for t in causes if t != "KRW=X"]
            if stock_causes:
                listed_dates = {listing_info[t][0] for t in stock_causes}
                if len(listed_dates) == 1:
                    who = ", ".join(display_name(t) for t in stock_causes)
                    reason = f"{who} 상장일이 {next(iter(listed_dates)):%Y-%m-%d}"
                else:
                    reason = ", ".join(f"{display_name(t)} 상장일이 {listing_info[t][0]:%Y-%m-%d}" for t in stock_causes)
                message = f"{reason} 이므로 조회 시작일을 수정했습니다."
                lagged = [t for t in stock_causes if (listing_info[t][1] - listing_info[t][0]).days > 7]
                if lagged:
                    message += f" (단, 시세 데이터가 {latest:%Y-%m-%d}부터 제공되어 그날부터 분석합니다.)"
            else:
                reason = f"USD/KRW 환율 데이터 시작일이 {latest:%Y-%m-%d}"
                message = f"{reason} 이므로 조회 시작일을 수정했습니다."
            start_ts = latest
            start_adjustment = {
                "requested": start_req.date(), "new_start": latest.date(),
                "causes": causes, "message": message,
                "listing_dates": {t: listing_info[t][0].date() for t in causes},
            }
            if start_ts >= end_ts:
                st.error(
                    f"❌ {reason}로, 조회 종료일({end_ts:%Y-%m-%d})보다 늦습니다. "
                    f"종료일을 늦추거나 종목을 변경하세요."
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
        kr_rate, us_rate, rate_note, rate_info = get_rate_series(
            idx, params["hedge_cost_mode"], params["manual_kr_rate"], params["manual_us_rate"],
        )
        # 구간 (t-1, t] 의 carry는 t-1 시점 금리 적용
        diff_prev = ((kr_rate - us_rate) / 100.0).shift(1).iloc[1:]
        carry = diff_prev * dt / DAY_COUNT
        avg_carry_pa = float(((kr_rate - us_rate)).mean())
        rate_daily = pd.DataFrame({
            "원화 단기금리(%)": kr_rate, "달러 단기금리(%)": us_rate,
            "금리차 원화-달러(%p)": kr_rate - us_rate,
        })
    else:
        carry = pd.Series(0.0, index=idx[1:])
        rate_note, avg_carry_pa = "해당 없음 (달러 자산 없음)", 0.0
        rate_info, rate_daily = {}, pd.DataFrame()

    # ── 5. 일별 총수익률 (현지통화) ──
    returns = prices.pct_change().iloc[1:]
    n_days = len(returns)
    R = returns[pt].to_numpy(dtype="float64")
    fx_col = fx_ret.reindex(returns.index).fillna(0.0).to_numpy(dtype="float64")[:, None]
    car_col = carry.reindex(returns.index).fillna(0.0).to_numpy(dtype="float64")[:, None]

    is_us = np.array([t in us_set for t in pt])
    is_krfx = np.array([t in KR_LISTED_US_FX for t in pt])

    # 종목별 환헤지 비율: 미국 국고채 / 미국 지수 ETF 각각 설정, 금(GLDM)은 환오픈
    h_user_vec = np.array([hedge_ratio_for(params, t) or 0.0 for t in pt], dtype="float64")

    def decompose(h_vec: np.ndarray):
        """
        원화 수익률 = 현지수익률 + 환효과 + 헤지carry   (h_vec: 종목별 헤지 비율)
        - 미국 상장(헤지비율 h): (1+r)(1+fx) − 1 − h·(fx − carry)
              → 현지 r / 환효과 (1−h)·fx + r·fx / carry h·carry
        - 국내상장 환노출 ETF: 현지 = (1+r)/(1+fx) − 1, 환효과 = r − 현지
        """
        local = R.copy()
        fxp = np.zeros_like(R)
        cp = np.zeros_like(R)
        if is_us.any():
            r_us = R[:, is_us]
            h_us = h_vec[is_us][None, :]
            fxp[:, is_us] = (1 - h_us) * fx_col + r_us * fx_col
            cp[:, is_us] = h_us * car_col
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

    local_u, fx_u, car_u = decompose(h_user_vec)
    port_open_arr = (weight_matrix * (local_u + fx_u + car_u)).sum(axis=1) + alpha_arr

    local_h, fx_h, car_h = decompose(np.ones(len(pt)))
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

    # ── 14. 내보내기용 상세 (AI 해설·검증) ──
    #   종목별 기여도: 위와 같은 linking·스케일 → 종목 합계 + 공모주 = 총수익률
    asset_rows = []
    for j, t in enumerate(pt):
        w_j = weight_matrix[:, j]
        c_loc = linked(w_j * local_u[:, j]) * scale
        c_fx = linked(w_j * fx_u[:, j]) * scale
        c_car = linked(w_j * car_u[:, j]) * scale
        ret_listing = (float(np.prod(1 + R[:, j])) - 1) * 100
        ret_krw = (float(np.prod(1 + local_u[:, j] + fx_u[:, j] + car_u[:, j])) - 1) * 100
        asset_rows.append({
            "종목코드": t.replace(".KS", ""),
            "종목명": ALL_NAMES.get(t, t),
            "자산군": CLASS_LABEL[ticker_class(params, t)],
            "상장통화": "USD" if t in us_set else "KRW",
            "환 유형": fx_type_label(t),
            "환헤지 비율(%)": None if hedge_ratio_for(params, t) is None else round(hedge_ratio_for(params, t) * 100, 1),
            "평균 비중(%)": round(float(w_j.mean()) * 100, 4),
            "상장통화 총수익률(%)": round(ret_listing, 4),
            "원화 환산 수익률(%, 헤지 반영)": round(ret_krw, 4),
            "현지수익 기여(%p)": round(c_loc, 4),
            "환차익 기여(%p)": round(c_fx, 4),
            "헤지손익 기여(%p)": round(c_car, 4),
            "합계 기여(%p)": round(c_loc + c_fx + c_car, 4),
        })
    asset_detail = pd.DataFrame(asset_rows)
    if not asset_detail.empty:
        cls_order = {CLASS_LABEL[k]: i for i, k in enumerate(["us_bond", "kr_bond", "us_eq", "kr_eq", "alt"])}
        asset_detail = (asset_detail.assign(_o=asset_detail["자산군"].map(cls_order))
                        .sort_values(["_o", "평균 비중(%)"], ascending=[True, False])
                        .drop(columns="_o").reset_index(drop=True))

    #   종목별 RAW 데이터 (백테스트에 실제로 쓰인 일별 값, 분석 캘린더 기준)
    ret_krw_all = local_u + fx_u + car_u
    pad = lambda arr: np.r_[np.nan, arr]                     # 기준일 행은 수익률 없음
    raw_sheets: dict[str, pd.DataFrame] = {}
    for j, t in enumerate(pt):
        d = pd.DataFrame(index=idx)
        d.index.name = "분석일"
        if t in raw:
            src = raw[t]
            pos = src.index.searchsorted(idx, side="right") - 1   # 각 분석일에 쓰인 원자료 행 (as-of)
            d["원자료 기준일"] = src.index[pos].date
            d["종가(분할 반영, 원자료)"] = src["close"].to_numpy()[pos]
            cumdiv = src["div"].cumsum().to_numpy()[pos]
            d["분배금(직전 행 이후 합계, 1주당)"] = np.r_[np.nan, np.diff(cumdiv)]
        else:
            d["원자료 기준일"] = idx.date
            d["합성 NAV(은대)"] = prices[t].to_numpy()
        d["총수익지수(분배 재투자, 시작=100)"] = (prices[t] / prices[t].iloc[0] * 100).to_numpy()
        d["일간 총수익률(상장통화, %)"] = pad(R[:, j] * 100)
        if (is_us[j] or is_krfx[j]) and has_fx:
            d["USD/KRW"] = fx_lvl.to_numpy()
            d["환율 변동(%)"] = pad(fx_col[:, 0] * 100)
        h_j = hedge_ratio_for(params, t)
        if h_j is not None:
            d["환헤지 비율(%)"] = h_j * 100
        d["현지수익(%)"] = pad(local_u[:, j] * 100)
        d["환효과(%)"] = pad(fx_u[:, j] * 100)
        d["헤지손익(%)"] = pad(car_u[:, j] * 100)
        d["원화 환산 수익률(%)"] = pad(ret_krw_all[:, j] * 100)
        d["적용 비중(%)"] = pad(weight_matrix[:, j] * 100)
        d["포트폴리오 기여(당일, %p)"] = pad(weight_matrix[:, j] * ret_krw_all[:, j] * 100)
        raw_sheets[t] = d

    port_sheet = pd.DataFrame(index=idx)
    port_sheet.index.name = "분석일"
    port_sheet["NAV 펀드(시작=100)"] = nav_open.to_numpy()
    port_sheet["일간 수익률(%)"] = pad(port_open_arr * 100)
    port_sheet["종목 기여 합계(%p)"] = pad((weight_matrix * ret_krw_all).sum(axis=1) * 100)
    port_sheet["공모주 Alpha(%p)"] = pad(alpha_arr * 100)
    port_sheet["TAA 적용(1=적용)"] = pad(taa_mask.astype(float))
    port_sheet["NAV 환헤지100%(시작=100)"] = nav_hedged.to_numpy()
    port_sheet["NAV S&P500 KRW 벤치마크(시작=100)"] = nav_bench.to_numpy()

    fx_sheet = pd.DataFrame(index=idx)
    fx_sheet.index.name = "분석일"
    if has_fx:
        fpos = fx_df.index.searchsorted(idx, side="right") - 1
        fx_sheet["USD/KRW 원자료 기준일"] = [fx_df.index[p].date() if p >= 0 else None for p in fpos]
        fx_sheet["USD/KRW"] = fx_lvl.to_numpy()
        fx_sheet["환율 변동(%)"] = pad(fx_col[:, 0] * 100)
    if not rate_daily.empty:
        fx_sheet = fx_sheet.join(rate_daily)
        fx_sheet["헤지 carry(당일, %)"] = pad(car_col[:, 0] * 100)

    #   월별 수익률 (%): 포트폴리오·벤치마크·종목(상장통화 총수익)·환율
    daily_tbl = pd.DataFrame({"포트폴리오": port_open, "S&P500(KRW) 벤치마크": bench_open}, index=returns.index)
    for j, t in enumerate(pt):
        daily_tbl[t.replace(".KS", "")] = R[:, j]
    daily_tbl["USD/KRW 변동"] = fx_ret.reindex(returns.index).fillna(0.0)
    monthly_returns = ((1 + daily_tbl).resample("ME").prod() - 1) * 100
    if has_fx:
        monthly_returns["USD/KRW 월말"] = fx_lvl.resample("ME").last().reindex(monthly_returns.index)
    if not rate_daily.empty:
        rm = rate_daily.resample("ME").last().reindex(monthly_returns.index)
        monthly_returns["원화 단기금리 월말(%)"] = rm["원화 단기금리(%)"]
        monthly_returns["달러 단기금리 월말(%)"] = rm["달러 단기금리(%)"]
    monthly_returns.index = monthly_returns.index.strftime("%Y-%m")
    monthly_returns.index.name = "월"

    #   검증 체크포인트: 공개 시세와 대조할 수 있는 시작·종료 종가 (분배 미반영 종가)
    checkpoints = []
    for t in avail_mkt:
        c = raw[t]["close"]
        c0, c1 = c.loc[:idx[0]], c.loc[:idx[-1]]
        if c0.empty or c1.empty:
            continue
        d_sum = float(raw[t]["div"].loc[(raw[t].index > c0.index[-1]) & (raw[t].index <= c1.index[-1])].sum())
        checkpoints.append({
            "종목코드": t.replace(".KS", ""),
            "종목명": ALL_NAMES.get(t, t),
            "통화": "USD" if t in us_set else "KRW",
            "시작 종가 기준일": c0.index[-1].date(),
            "시작 종가": round(float(c0.iloc[-1]), 4),
            "종료 종가 기준일": c1.index[-1].date(),
            "종료 종가": round(float(c1.iloc[-1]), 4),
            "가격 수익률(%)": round((float(c1.iloc[-1]) / float(c0.iloc[-1]) - 1) * 100, 4),
            "기간 분배금 합계(1주당)": round(d_sum, 4),
            "총수익률(%, 분배 재투자)": round((float(prices[t].iloc[-1]) / float(prices[t].iloc[0]) - 1) * 100, 4),
        })
    fx_check = None
    if has_fx:
        f = fx_df["close"]
        f0, f1 = f.loc[:idx[0]], f.loc[:idx[-1]]
        if not f0.empty and not f1.empty:
            fx_check = {
                "출처": "Yahoo Finance KRW=X",
                "시작 기준일": f0.index[-1].date(), "시작 환율": round(float(f0.iloc[-1]), 4),
                "종료 기준일": f1.index[-1].date(), "종료 환율": round(float(f1.iloc[-1]), 4),
                "변동률(%)": round((float(f1.iloc[-1]) / float(f0.iloc[-1]) - 1) * 100, 4),
            }

    hb_pct = params.get("hedge_us_bond", params.get("hedge_ratio", 0))
    he_pct = params.get("hedge_us_eq", params.get("hedge_ratio", 0))
    hedge_label = f"미국채 {hb_pct}% · 미국주식 {he_pct}%"
    hedged_share = float(sum(weights.get(t, 0.0) * (hedge_ratio_for(params, t) or 0.0) for t in pt)) * 100

    params_snapshot = {
        "요청 시작일": start_req.date(), "요청 종료일": end_ts.date(),
        "자산군 비중 입력(%)": {
            "미국 국고채": params["weight_us_bond"], "한국 국고채": params["weight_kr_bond"],
            "미국 지수 ETF": params["weight_us_eq"], "한국 지수 ETF": params["weight_kr_eq"],
            "대체·현금성": params["weight_alt_cash"],
        },
        "선택 종목": {
            "미국 국고채": params["us_bonds"], "한국 국고채": params["kr_bonds"],
            "미국 지수 ETF": params["us_equity"], "한국 지수 ETF": params["kr_equity"],
            "금(GLDM)": params["gold_enabled"], "현금성": params["cash_ticker"],
        },
        "공모주 Alpha 가정(연 %p)": params["ipo_alpha"],
        "자산군 내 종목 비중 입력(%)": params.get("splits", {}),
        "환헤지 비율(%)": {"미국 국고채": hb_pct, "미국 지수 ETF": he_pct, "금(GLDM)": "환오픈"},
        "포트폴리오 기준 실효 헤지 비중(%)": round(hedged_share, 4),
        "헤지 금리 산출": params["hedge_cost_mode"],
        "수동 금리(원화/달러, %)": [params["manual_kr_rate"], params["manual_us_rate"]],
        "RSI TAA": ({"사용": True, "기간": params["rsi_period"], "진입": params["rsi_entry"],
                     "탈출": params["rsi_exit"], "최대 유지일": params["rsi_max_days"]}
                    if params["rsi_taa_enabled"] else {"사용": False}),
        "턴어라운드 연도": params["turnaround_years"] if params["turnaround_enabled"] else [],
        "TAA 적용 영업일 수": int((taa_signal > 0).sum()),
    }

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
        "rate_info":            rate_info,
        "rate_daily":           rate_daily,
        "hedge_cost_mode":      params["hedge_cost_mode"],
        "hedge_us_bond":        hb_pct,
        "hedge_us_eq":          he_pct,
        "hedge_label":          hedge_label,
        "hedged_share":         hedged_share,
        "weight_table":         weight_table(params, weights),
        "taa_days_rsi":         taa_days_rsi,
        "start_adjustment":     start_adjustment,
        "requested_start":      start_req.date(),
        "asset_detail":         asset_detail,
        "monthly_returns":      monthly_returns,
        "checkpoints":          checkpoints,
        "fx_check":             fx_check,
        "params_snapshot":      params_snapshot,
        "raw_sheets":           raw_sheets,
        "raw_portfolio":        port_sheet,
        "raw_fx_rates":         fx_sheet,
        "run_id":               f"{pd.Timestamp.now().value}",
    }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SIDEBAR UI (파라미터 제어)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def render_split_inputs(cls: str, tickers: list[str], class_w: float) -> dict[str, float]:
    """
    자산군 안의 종목별 비중 입력 (종목이 2개 이상일 때만 표시).
    반환: {ticker: 입력 비중(%)} — 합계가 100이 아니면 계산 시 100%로 정규화.
    """
    if len(tickers) <= 1:
        return {t: 100.0 for t in tickers}
    ss = st.session_state
    base_eq = round(100.0 / len(tickers), 1)
    # 균등 배분 (합계가 정확히 100이 되도록 마지막 종목에 나머지)
    equal = {t: base_eq for t in tickers}
    equal[tickers[-1]] = round(100.0 - base_eq * (len(tickers) - 1), 1)
    sel_key = f"split_sel_{cls}"
    # 종목 구성이 바뀌면 균등 배분으로 다시 시작
    if ss.get(sel_key) != tuple(tickers):
        for t in tickers:
            ss[f"split_{cls}_{t}"] = equal[t]
        ss[sel_key] = tuple(tickers)

    def _reset_equal():
        for t in tickers:
            st.session_state[f"split_{cls}_{t}"] = equal[t]

    st.caption(f"↳ **{CLASS_LABEL[cls]} 종목별 비중** (자산군 {class_w}% 안에서 나눔)")
    vals: dict[str, float] = {}
    for t in tickers:
        code = t.replace(".KS", "")
        vals[t] = float(st.number_input(
            f"{code} · {ALL_NAMES.get(t, t).split(' (')[0]}{listing_tag(t)} — 자산군 내 %",
            min_value=0.0, max_value=100.0, step=5.0, format="%.1f", key=f"split_{cls}_{t}",
        ))
    tot = sum(vals.values())
    parts = " · ".join(
        f"{t.replace('.KS', '')} {class_w * v / tot:.1f}%" for t, v in vals.items()
    ) if tot > 0 else "-"
    if tot <= 0:
        st.warning(f"⚠️ {CLASS_LABEL[cls]} 종목 비중이 모두 0%입니다. 이 자산군은 편입되지 않습니다.")
    elif abs(tot - 100) > 0.05:
        st.caption(f"합계 {tot:.1f}% → 100%로 정규화 | 포트폴리오 기준: {parts}")
    else:
        st.caption(f"포트폴리오 기준: {parts}")
    st.button("균등 배분으로 초기화", key=f"split_eq_{cls}", on_click=_reset_equal)
    return vals


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
            st.caption("🇺🇸 **미국 국채 ETF** (미국 상장 + 국내상장, (H)=환헤지형)")
            us_bonds = st.multiselect(
                "미국 국채", list(US_BOND.keys()), default=["IEF", "TLT"],
                format_func=lambda x: (
                    f"{x.replace('.KS','')} - {US_BOND[x]}"
                    + listing_tag(x)
                ),
                label_visibility="collapsed",
            )

            st.caption("🇰🇷 **한국 국고채 ETF** (.KS 자동 매핑)")
            kr_bonds = st.multiselect(
                "한국 국고채", list(KR_BOND.keys()), default=["471230.KS"],
                format_func=lambda x: (
                    f"{x.replace('.KS','')} - {KR_BOND[x]}"
                    + listing_tag(x)
                ),
                label_visibility="collapsed",
            )

        with st.expander("📈 지수 ETF 유니버스 (미국·한국)", expanded=True):
            st.caption("🇺🇸 **미국 지수 ETF** (S&P500 / NASDAQ100)")
            us_equity = st.multiselect(
                "미국 지수 ETF", list(US_EQUITY.keys()), default=["VOO"],
                format_func=lambda x: (
                    f"{x.replace('.KS','')} - {US_EQUITY[x]}"
                    + listing_tag(x)
                ),
                label_visibility="collapsed",
            )

            st.caption("🇰🇷 **한국 지수 ETF** (코스피200)")
            kr_equity = st.multiselect(
                "한국 지수 ETF", list(KR_EQUITY.keys()), default=["102110.KS"],
                format_func=lambda x: (
                    f"{x.replace('.KS','')} - {KR_EQUITY[x]}"
                    + listing_tag(x)
                ),
                label_visibility="collapsed",
            )

        # ── 3. 대체 및 현금성 자산 ──
        with st.expander("🏆 대체·현금성 자산", expanded=False):
            gold_on = st.toggle(f"Gold (GLDM) 편입{listing_tag('GLDM')}", value=False)
            cash_ticker = st.selectbox(
                "현금성 자산 선택", list(CASH_OPTS.keys()),
                format_func=lambda x: (
                    f"{x.replace('.KS','')} - {CASH_OPTS[x]}{listing_tag(x)}"
                    if x != "BANK_DEPOSIT" else CASH_OPTS[x]
                ),
            )

        # ── 4. 투자비중 슬라이더 (자산군 비중 + 자산군 내 종목별 비중) ──
        with st.expander("⚖️ 자산배분 비중 설정 (목표 8% 포트폴리오)", expanded=True):
            st.caption("💡 **설계 원칙**: 국채 90% 수준 + 지수 ETF 10% 수준")
            st.caption("한 자산군에 종목을 2개 이상 고르면 아래에 종목별 비중 입력칸이 나타납니다.")

            weight_us_bond = st.slider("미국 국고채 비중 (%)", 0, 100, 45, 5)
            split_us_bond = render_split_inputs("us_bond", us_bonds, weight_us_bond)
            weight_kr_bond = st.slider("한국 국고채 비중 (%)", 0, 100, 45, 5)
            split_kr_bond = render_split_inputs("kr_bond", kr_bonds, weight_kr_bond)
            weight_us_eq = st.slider("미국 지수 ETF 비중 (%)", 0, 30, 10, 1)
            split_us_eq = render_split_inputs("us_eq", us_equity, weight_us_eq)
            weight_kr_eq = st.slider("한국 지수 ETF 비중 (%)", 0, 30, 0, 1)
            split_kr_eq = render_split_inputs("kr_eq", kr_equity, weight_kr_eq)
            weight_alt_cash = st.slider("대체(Gold)/현금성 자산 비중 (%)", 0, 20, 0, 1)
            splits = {"us_bond": split_us_bond, "kr_bond": split_kr_bond,
                      "us_eq": split_us_eq, "kr_eq": split_kr_eq}

            total_raw_w = weight_us_bond + weight_kr_bond + weight_us_eq + weight_kr_eq + weight_alt_cash
            if total_raw_w == 100:
                st.success(f"합계 비중: **{total_raw_w}%** (정상)")
            else:
                st.info(f"합계: **{total_raw_w}%** → 포트폴리오 편입 시 **100% 자동 정규화** 적용")

            # 위에서 조절한 비중대로 최종 편입 비중 미리보기
            preview_params = {
                "us_bonds": us_bonds, "kr_bonds": kr_bonds, "us_equity": us_equity, "kr_equity": kr_equity,
                "gold_enabled": gold_on, "cash_ticker": cash_ticker, "splits": splits,
                "weight_us_bond": weight_us_bond, "weight_kr_bond": weight_kr_bond,
                "weight_us_eq": weight_us_eq, "weight_kr_eq": weight_kr_eq, "weight_alt_cash": weight_alt_cash,
            }
            preview_cands = list(dict.fromkeys(
                us_bonds + kr_bonds + us_equity + kr_equity
                + (["GLDM"] if gold_on else []) + ([cash_ticker] if cash_ticker else [])
            ))
            preview_w, preview_cat = _calc_weights(preview_params, preview_cands)
            if preview_w:
                st.markdown("**📋 최종 편입 비중 (포트폴리오 기준)**")
                cat_line = " · ".join(f"{k} {v * 100:.1f}%" for k, v in preview_cat.items() if v > 0)
                st.caption(cat_line)
                st.dataframe(
                    weight_table(preview_params, preview_w, with_hedge=False)
                    .drop(columns=["종목명"]),
                    hide_index=True, use_container_width=True,
                )
                if weight_us_bond > 0 and not us_bonds:
                    st.caption("ℹ️ 미국 국고채 종목이 없어 그 비중은 한국 국고채로 옮겨 계산합니다.")
            st.caption("비중 0%인 자산군·종목은 공통 구간 계산에서 제외됩니다. "
                       "데이터가 없는 종목이 빠지면 실제 비중은 결과 화면에서 확인하세요.")

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
            st.caption("헤지 비율은 각 자산군의 **미국 상장(달러) 종목 편입분**에 대한 비율입니다. "
                       "(예: 미국 상장 국채 50% 편입 + 헤지 30% → 포트폴리오의 15%를 헤지)")
            hedge_us_bond = st.slider(
                "🇺🇸 미국 국채 환헤지 (%)", 0, 100, 0, 5, key="hedge_us_bond",
                help="미국 상장 국채 ETF(SGOV·SHY·IEI·IEF·TLT) 편입분 중 환헤지하는 비율. 0% = 환오픈, 100% = 완전 헤지",
            )
            hedge_us_eq = st.slider(
                "🇺🇸 미국 지수 ETF 환헤지 (%)", 0, 100, 0, 5, key="hedge_us_eq",
                help="미국 상장 지수 ETF(VOO·QQQM) 편입분 중 환헤지하는 비율. 0% = 환오픈, 100% = 완전 헤지",
            )
            if preview_w:
                def _w(cls_key, cond):
                    return sum(w for t, w in preview_w.items()
                               if ticker_class(preview_params, t) == cls_key and cond(t)) * 100
                usd_b, usd_e = _w("us_bond", is_usd_listed), _w("us_eq", is_usd_listed)
                hedged_b, hedged_e = usd_b * hedge_us_bond / 100, usd_e * hedge_us_eq / 100
                gold_w = preview_w.get("GLDM", 0.0) * 100
                kr_open = sum(w for t, w in preview_w.items() if t in KR_LISTED_US_FX) * 100
                kr_h = sum(w for t, w in preview_w.items() if t in KR_LISTED_HEDGED) * 100
                open_total = (usd_b - hedged_b) + (usd_e - hedged_e) + gold_w + kr_open
                st.caption(
                    f"미국 상장 국채 {usd_b:.1f}% × {hedge_us_bond}% = **{hedged_b:.1f}%** 헤지  \n"
                    f"미국 상장 지수 {usd_e:.1f}% × {hedge_us_eq}% = **{hedged_e:.1f}%** 헤지  \n"
                    + (f"금(GLDM) {gold_w:.1f}% = 환오픈  \n" if gold_w > 0 else "")
                    + (f"국내상장 환노출 ETF {kr_open:.1f}% = 환노출 (헤지 불가)  \n" if kr_open > 0 else "")
                    + (f"국내상장 (H) ETF {kr_h:.1f}% = 상품 자체 헤지  \n" if kr_h > 0 else "")
                    + f"→ 포트폴리오 기준 달러 환노출 **{open_total:.1f}%**, "
                      f"헤지 {hedged_b + hedged_e + kr_h:.1f}% (슬라이더 {hedged_b + hedged_e:.1f}% + (H) {kr_h:.1f}%)"
                )
            st.caption("국내상장 종목은 슬라이더 대상이 아닙니다. 환노출형은 그대로 환노출, (H)형은 상품 안에서 이미 헤지됩니다.")
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
            st.caption("실제로 끌어온 금리 값은 결과 화면의 **💱 헤지 금리 상세**와 엑셀 '헤지금리' 시트에서 확인할 수 있습니다.")

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
        "hedge_us_bond":    hedge_us_bond,
        "hedge_us_eq":      hedge_us_eq,
        "splits":           splits,
        "show_hedged_line": show_hedged,
        "hedge_cost_mode":  hedge_cost_mode,
        "manual_kr_rate":   manual_kr_rate,
        "manual_us_rate":   manual_us_rate,
    }
    return params, run_clicked

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  헤지 금리 상세 (자동 조회값 확인용)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def rate_summary_df(res: dict) -> pd.DataFrame:
    """원화·달러 금리와 금리차의 출처·최신값·기간 통계 표."""
    info = res.get("rate_info") or {}
    rd = res.get("rate_daily")
    if not info or rd is None or rd.empty:
        return pd.DataFrame()
    rows = []
    for ccy, label in (("KRW", "원화 단기금리"), ("USD", "달러 단기금리")):
        d = info[ccy]
        rows.append({
            "구분": label,
            "출처": d["출처"],
            "자료 주기": d["주기"],
            "원자료 기준일": f"{d['원자료 최신 기준일']:%Y-%m-%d}" if d["원자료 최신 기준일"] else "-",
            "원자료 최신값(%)": round(d["원자료 최신값(%)"], 3),
            "분석 시작일 값(%)": round(d["분석 시작일 값(%)"], 3),
            "분석 종료일 값(%)": round(d["분석 종료일 값(%)"], 3),
            "기간 평균(%)": round(d["기간 평균(%)"], 3),
            "기간 최저(%)": round(d["기간 최저(%)"], 3),
            "기간 최고(%)": round(d["기간 최고(%)"], 3),
        })
    sp = rd["금리차 원화-달러(%p)"]
    rows.append({
        "구분": "금리차 (원화 − 달러)", "출처": "계산값", "자료 주기": "-", "원자료 기준일": "-",
        "원자료 최신값(%)": round(rows[0]["원자료 최신값(%)"] - rows[1]["원자료 최신값(%)"], 3),
        "분석 시작일 값(%)": round(float(sp.iloc[0]), 3),
        "분석 종료일 값(%)": round(float(sp.iloc[-1]), 3),
        "기간 평균(%)": round(float(sp.mean()), 3),
        "기간 최저(%)": round(float(sp.min()), 3),
        "기간 최고(%)": round(float(sp.max()), 3),
    })
    return pd.DataFrame(rows)


def render_rate_details(res: dict):
    """분석에 실제 사용된 헤지 금리를 확인할 수 있는 상세 패널."""
    info = res.get("rate_info") or {}
    rd = res.get("rate_daily")
    if not info or rd is None or rd.empty:
        st.caption(f"헤지 금리: {res.get('rate_note', '-')}")
        return

    used_manual = [c for c in info if info[c]["수동값 사용"]]
    auto_failed = res.get("hedge_cost_mode") == "자동" and bool(used_manual)
    kr_end, us_end = info["KRW"]["분석 종료일 값(%)"], info["USD"]["분석 종료일 값(%)"]
    title = (f"💱 헤지 금리 상세 — 원화 {kr_end:.2f}% / 달러 {us_end:.2f}% "
             f"(금리차 {kr_end - us_end:+.2f}%p, 분석 종료일 기준)")
    with st.expander(title, expanded=auto_failed):
        if auto_failed:
            names = ", ".join("원화" if c == "KRW" else "달러" for c in used_manual)
            st.warning(f"⚠️ {names} 금리는 자동 조회에 실패해 사이드바의 수동 입력값을 사용했습니다.")

        st.dataframe(rate_summary_df(res), hide_index=True, use_container_width=True)

        for ccy, label in (("KRW", "원화"), ("USD", "달러")):
            d = info[ccy]
            if not d["수동값 사용"] and d["최신값 경과일"] > 45:
                st.caption(
                    f"⚠️ {label} 금리 원자료의 마지막 값은 "
                    f"{d['원자료 최신 기준일']:%Y-%m}{' 월평균' if d['주기'] == '월평균' else ''} 기준입니다. "
                    f"그 이후 {d['최신값 경과일']}일은 이 값({d['원자료 최신값(%)']:.2f}%)을 그대로 사용했습니다."
                )
        st.caption(
            "ℹ️ 원화: FRED 한국 3개월 금리는 **월평균**이며 날짜는 해당 월 1일로 표기됩니다 (그 달 내내 같은 값 적용). "
            "달러: ^IRX는 미 T-bill 13주 할인율(연 %)입니다. "
            "각 영업일의 헤지 손익에는 **전 영업일의 금리차**를 적용합니다."
        )

        fig_r = go.Figure()
        fig_r.add_trace(go.Scatter(x=rd.index, y=rd["원화 단기금리(%)"], name="원화 단기금리",
                                   line=dict(color="#1565C0", width=1.8)))
        fig_r.add_trace(go.Scatter(x=rd.index, y=rd["달러 단기금리(%)"], name="달러 단기금리",
                                   line=dict(color="#E65100", width=1.8)))
        fig_r.add_trace(go.Scatter(x=rd.index, y=rd["금리차 원화-달러(%p)"], name="금리차 (원화−달러)",
                                   line=dict(color="#6D4C41", width=1.4, dash="dot")))
        fig_r.add_hline(y=0, line_color="#9E9E9E", line_width=1)
        fig_r.update_layout(
            template="plotly_white", hovermode="x unified", height=300,
            yaxis_title="연 %", legend=dict(orientation="h", y=1.15, x=0.5, xanchor="center"),
            margin=dict(l=10, r=10, t=30, b=10),
        )
        st.plotly_chart(fig_r, use_container_width=True)

        st.markdown("##### 월별 사용 금리 (각 월 마지막 영업일 값)")
        monthly = rd.resample("ME").last().dropna(how="all")
        monthly.index = monthly.index.strftime("%Y-%m")
        monthly.index.name = "월"
        st.dataframe(monthly.round(3).iloc[::-1], use_container_width=True, height=260)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AI 해설·검증용 데이터 내보내기
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AI_PROMPT = """당신은 자산운용사 리서치 애널리스트입니다. 아래 데이터는 '국채·지수 ETF 혼합형 펀드'의 가상 백테스트 결과입니다.
다음 세 가지 작업을 순서대로 수행해 주세요.

[작업 1] 값 검증
 1) 내부 정합성: (a) '월별 수익률'의 포트폴리오 값을 복리로 연결한 결과가 '핵심 지표'의 누적 수익률과 맞는지,
    (b) '성과 기여도' 항목 합계가 합산 실현치와 같은지, (c) '종목별 상세'의 합계 기여 + 공모주 Alpha가 총수익률과 같은지 확인하세요.
    (표시 자릿수 반올림 때문에 0.01%p 이내 차이는 일치로 판단하세요.)
 2) 외부 대조: '검증 체크포인트'의 종목별 시작·종료 종가, USD/KRW 환율, '헤지 금리'의 원화·달러 금리를
    공개 자료(거래소·운용사 공시, 한국은행 ECOS, FRED, 미 재무부 등)와 대조하세요.
    차이가 있으면 원인(분배금 재투자 여부, 미국 종가와 한국 영업일의 날짜 시차, 데이터 소스 차이 등)을 추정하세요.
 3) 상식 점검: 기간 중 미국·한국 국채 금리 변화 방향과 채권 ETF 수익률(듀레이션 감안)이 맞는지,
    지수 ETF 수익률이 해당 지수 흐름과 맞는지, 환차익 기여가 USD/KRW 변동과 맞는지 대략 추정해 보세요.

[작업 2] 해설
 - 수익 원천별(국채 / 지수 / 환차익 / 환헤지 손익 / 금·현금성 / 공모주 Alpha)로 왜 이런 값이 나왔는지,
   기간 중 시황과 경제 이슈(연준·한국은행 통화정책, 국채 금리, 환율, 주식시장 주요 이벤트)를 근거로 설명하세요.
 - '연도별 수익률'과 '주요 낙폭 구간'의 원인을 날짜와 연결해 설명하세요.
 - 목표 수익률 8% 대비 달성 여부와 그 이유를 정리하세요.

[작업 3] 한계와 시사점
 - '가정 및 한계'에 적힌 가정이 결과에 미쳤을 영향(특히 공모주 Alpha는 입력 가정치이며 실제 성과가 아님)을 평가하세요.
 - 이 결과가 앞으로도 재현될 수 있는 조건과 리스크를 정리하세요.

[규칙]
 - 확인된 사실과 추정을 구분해 표시하세요. 외부 자료를 인용할 때는 출처와 기준일을 밝히세요.
 - 확인할 수 없는 시황이나 수치는 지어내지 말고 '확인 필요'로 남기세요. 데이터에 없는 값을 만들지 마세요.

[출력 형식]
 1) 검증 결과 요약표 (항목 / 결과: 일치·불일치·확인 불가 / 근거)
 2) 수익 원천별 해설
 3) 연도별·낙폭 구간 해설
 4) 리스크와 시사점
"""

EXPORT_ASSUMPTIONS = [
    "가상 백테스트이며 실제 운용 성과가 아님. 거래비용·세금·운용보수 외 비용은 반영하지 않음 (ETF 총보수는 가격에 반영됨).",
    "비중은 매 영업일 목표 비중으로 리밸런싱한다고 가정 (TAA 적용일은 주식 비중 30%로 확대).",
    "총수익 = Yahoo Finance 분할 반영 종가 + 분배금 재투자. Yahoo 데이터에 분배금이 누락된 종목은 총수익이 과소 계산될 수 있음.",
    "한국 종목이 있으면 한국 영업일 기준 캘린더를 사용하고, 미국 종목은 직전 미국 종가를 사용 (날짜 시차 존재).",
    "환율은 Yahoo Finance KRW=X 사용. 미국 상장 자산의 원화 수익률 = (1+현지수익률)(1+환율변동) − 1 − 헤지비율×(환율변동 − 금리차). 헤지비율은 미국 국고채·미국 지수 ETF에 각각 따로 적용하고, 금(GLDM)은 환오픈.",
    "헤지 손익(금리차)은 전 영업일의 (원화 단기금리 − 달러 단기금리) × 경과일/365로 근사. 원화 금리는 FRED 월평균 자료.",
    "국내상장 환노출 ETF(종목별 상세의 '환 유형' 참고)는 원화 가격에서 환율 효과를 분리해 현지수익 기여와 환차익 기여로 나눔. 미국 종가와 한국 종가의 시차 때문에 일별 분해에는 오차가 있음.",
    "국내상장 환헤지형(H) ETF는 원화 자산처럼 처리함: 헤지 비용이 이미 가격에 들어 있어 환차익·헤지손익 기여는 0으로 표시되고 전부 현지수익에 포함됨. 환헤지 슬라이더는 미국 상장 종목에만 적용.",
    "공모주 Alpha는 사용자가 입력한 연간 가정치를 달력일 기준으로 일할 가산한 값 (실제 공모주 성과 아님).",
    "은대(BANK_DEPOSIT)는 연 2.53% 고정 금리를 달력일 기준(ACT/365)으로 일할한 합성 자산.",
    "샤프 지수의 무위험수익률은 연 3% 고정.",
    "조회 시작일은 선택 종목 중 가장 늦게 상장한 종목의 상장일(공식 상장일이 등록된 종목은 그 날짜, 그 외는 시세 데이터 첫 거래일) 또는 USD/KRW 데이터 시작일로 자동 보정됨.",
]


def top_drawdowns(nav: pd.Series, n: int = 3) -> pd.DataFrame:
    """겹치지 않는 낙폭 구간 상위 n개 (고점일·저점일·회복일·낙폭)."""
    dd = nav / nav.cummax() - 1
    covered = pd.Series(False, index=nav.index)
    rows = []
    for _ in range(n):
        cand = dd[~covered]
        if cand.empty or cand.min() >= -1e-9:
            break
        trough = cand.idxmin()
        before = dd.loc[:trough]
        peak = before[before >= -1e-12].index[-1]
        after = dd.loc[trough:]
        rec = after[after >= -1e-12]
        recovery = rec.index[0] if len(rec) else None
        covered.loc[peak:(recovery or nav.index[-1])] = True
        rows.append({
            "순위": len(rows) + 1,
            "고점일": peak.date(), "저점일": trough.date(),
            "회복일": recovery.date() if recovery is not None else "미회복",
            "낙폭(%)": round(float(dd.loc[trough]) * 100, 4),
            "하락 기간(일)": (trough - peak).days,
            "회복 기간(일)": (recovery - trough).days if recovery is not None else None,
        })
    return pd.DataFrame(rows)


def _jsonable(o):
    """JSON 직렬화: 날짜→문자열, NaN→null, numpy→파이썬 기본형."""
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, pd.DataFrame):
        return [_jsonable(r) for r in o.to_dict("records")]
    if isinstance(o, pd.Series):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (pd.Timestamp, date)):
        return o.strftime("%Y-%m-%d")
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else round(float(o), 6)
    return o


def build_ai_export(res: dict) -> dict:
    """AI 해설·검증에 넘길 구조화 데이터."""
    is_short = res["is_short_term"]
    attr = res["attribution"]
    nav_b = res["nav_benchmark"]
    bench_ret = nav_b.pct_change().dropna()
    ppy = res.get("periods_per_year", 252.0)
    unit = "기간 누적(%p)" if is_short else "연환산 CAGR 기준(%p)"

    yearly = pd.DataFrame({
        "연도": res["yearly_portfolio"].index,
        "포트폴리오(%)": res["yearly_portfolio"].values,
        "S&P500(KRW)(%)": res["yearly_benchmark"].reindex(res["yearly_portfolio"].index).values,
        "환헤지 100%(%)": res["yearly_hedged"].reindex(res["yearly_portfolio"].index).values,
    })
    adj = res.get("start_adjustment")
    start_is_listing = bool(adj) and abs((res["analysis_start"] - pd.Timestamp(adj["new_start"])).days) <= PARTIAL_YEAR_GRACE_DAYS
    labels, notes = yearly_labels(yearly["연도"], res["analysis_start"], res["analysis_end"], start_is_listing)
    yearly["표기"], yearly["비고"] = labels, notes

    monthly = res["monthly_returns"].reset_index()

    asset_sum = float(res["asset_detail"]["합계 기여(%p)"].sum()) if not res["asset_detail"].empty else 0.0
    payload = {
        "개요": {
            "생성 시각": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
            "내용": "국채·지수 ETF 혼합형 펀드 가상 백테스트 결과",
            "통화 기준": "KRW",
            "분석 구간": {
                "시작": res["analysis_start"], "종료": res["analysis_end"],
                "달력일": res["total_days"], "영업일 수": res["trading_days"],
                "기준 캘린더": res.get("calendar_label"),
            },
            "단기 모드(1년 미만)": is_short,
            "조회 시작일 보정": adj,
        },
        "설정": res.get("params_snapshot", {}),
        "실효 비중(%)": {k: v * 100 for k, v in res["weights"].items()},
        "종목별 비중 상세": res["weight_table"],
        "핵심 지표": {
            "포트폴리오": {
                "누적 수익률(%)": res["cumulative_return"],
                ("연환산 수익률(%)" if is_short else "CAGR(%)"): res["cagr"],
                "목표 8% 대비(%p)": None if is_short else res["cagr"] - 8.0,
                "연환산 변동성(%)": res["volatility"],
                "샤프 지수(Rf 3%)": res["sharpe"],
                "최대 낙폭 MDD(%)": res["mdd"],
                "환헤지 100% 가정 CAGR(%)": res["cagr_hedged"],
            },
            "벤치마크 S&P500(KRW)": {
                "누적 수익률(%)": res["benchmark_cumulative"],
                ("연환산 수익률(%)" if is_short else "CAGR(%)"): calc_returns_and_cagr(nav_b)[1],
                "연환산 변동성(%)": calc_volatility(bench_ret, ppy),
                "샤프 지수(Rf 3%)": calc_sharpe(bench_ret, res.get("dt_days"), ppy),
                "최대 낙폭 MDD(%)": calc_mdd(nav_b),
            },
        },
        "성과 기여도": {
            "단위": unit,
            "① 국채 ETF": attr["bond_contrib"], "② 지수 ETF": attr["eq_contrib"],
            "③ 환차익": attr["fx_contrib"], "④ 공모주 Alpha(가정치)": attr["ipo_contrib"],
            "⑤ 금·현금성": attr["alt_contrib"], "⑥ 환헤지 손익(금리차)": attr["carry_contrib"],
            "합산 실현치": attr["total_cagr"],
            "합계 검증 오차": attr["check_gap"],
            "설계 목표 모델": {"① 국채 ETF": "3~4%p", "② 지수 ETF": "0~3%p", "③ 환차익": "3~5%p",
                           "④ 공모주 Alpha": "0~1%p", "합산": "8~10%"},
        },
        "종목별 상세": {
            "단위": unit,
            "설명": "합계 기여 = 현지수익 + 환차익 + 헤지손익. 종목 합계 + 공모주 Alpha = 합산 실현치 (반올림 오차 0.01%p 이내). "
                  "TAA 적용일에는 주식 비중이 커지므로, 그 기간 주식 수익이 기여도에 더 크게 반영됨.",
            "종목 합계 기여(%p)": asset_sum,
            "표": res["asset_detail"],
        },
        "연도별 수익률": yearly,
        "주요 낙폭 구간": top_drawdowns(res["nav_open"]),
        "월별 수익률(%)": {
            "설명": "포트폴리오·벤치마크는 원화 기준. 종목 열은 상장통화 기준 총수익률(분배 재투자). "
                  "USD/KRW 변동은 월간 환율 변동률, 월말 열은 수준값.",
            "표": monthly,
        },
        "헤지 금리": {
            "출처 요약": res.get("rate_note"),
            "기간 평균 금리차(%p)": res.get("avg_carry_pa"),
            "요약": rate_summary_df(res),
        },
        "검증 체크포인트": {
            "설명": "공개 시세와 대조용. 종가는 분배 미반영(분할만 반영). 미국 종목의 기준일은 한국 영업일 기준 직전 미국 거래일일 수 있음.",
            "종목 종가": res.get("checkpoints", []),
            "USD/KRW": res.get("fx_check"),
        },
        "가정 및 한계": EXPORT_ASSUMPTIONS,
    }
    return _jsonable(payload)


def _md_cell(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:,.4f}".rstrip("0").rstrip(".") if abs(v) < 1e6 else f"{v:,.0f}"
    return str(v).replace("|", "/").replace("\n", " ")


def _md_table(rows: list[dict]) -> str:
    if not rows:
        return "(데이터 없음)\n"
    cols = list(rows[0].keys())
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(_md_cell(r.get(c)) for c in cols) + " |")
    return "\n".join(out) + "\n"


def _md_kv(d: dict, indent: str = "") -> str:
    lines = []
    for k, v in d.items():
        if isinstance(v, dict):
            lines.append(f"{indent}- **{k}**")
            lines.append(_md_kv(v, indent + "  "))
        else:
            lines.append(f"{indent}- {k}: {_md_cell(v) if not isinstance(v, list) else ', '.join(map(str, v)) or '-'}")
    return "\n".join(lines)


def render_ai_markdown(payload: dict, include_prompt: bool = True) -> str:
    """AI 채팅에 그대로 붙여 넣을 수 있는 Markdown 문서."""
    p = payload
    parts = []
    if include_prompt:
        parts += ["# 요청", "", AI_PROMPT, "", "---", ""]
    parts += ["# 백테스트 결과 데이터", ""]
    parts += ["## 개요", _md_kv(p["개요"]), ""]
    parts += ["## 설정", _md_kv(p["설정"]), ""]
    parts += ["## 종목별 비중", _md_table(p["종목별 비중 상세"])]
    parts += ["## 핵심 지표", _md_kv(p["핵심 지표"]), ""]
    parts += ["## 성과 기여도", _md_kv(p["성과 기여도"]), ""]
    sd = p["종목별 상세"]
    parts += ["## 종목별 상세", f"단위: {sd['단위']} · {sd['설명']} · 종목 합계 기여 {_md_cell(sd['종목 합계 기여(%p)'])}%p", "",
              _md_table(sd["표"])]
    parts += ["## 연도별 수익률", _md_table(p["연도별 수익률"])]
    parts += ["## 주요 낙폭 구간", _md_table(p["주요 낙폭 구간"])]
    hg = p["헤지 금리"]
    parts += ["## 헤지 금리", f"출처: {hg['출처 요약']} · 기간 평균 금리차 {_md_cell(hg['기간 평균 금리차(%p)'])}%p", "",
              _md_table(hg["요약"])]
    cp = p["검증 체크포인트"]
    parts += ["## 검증 체크포인트", cp["설명"], "", _md_table(cp["종목 종가"])]
    if cp["USD/KRW"]:
        parts += ["USD/KRW: " + ", ".join(f"{k} {_md_cell(v)}" for k, v in cp["USD/KRW"].items()), ""]
    mr = p["월별 수익률(%)"]
    parts += ["## 월별 수익률(%)", mr["설명"], "", _md_table(mr["표"])]
    parts += ["## 가정 및 한계"] + [f"- {a}" for a in p["가정 및 한계"]] + [""]
    return "\n".join(parts)


def render_ai_export_section(res: dict):
    """대시보드 하단: AI 해설·검증용 내보내기."""
    st.subheader("🤖 AI 해설·검증용 데이터 내보내기")
    st.caption(
        "분석 결과를 AI에게 넘겨 **값 검증**과 **시황 기반 해설**을 받을 수 있도록 구조화한 데이터입니다. "
        "Markdown 파일에는 AI 요청 프롬프트가 맨 앞에 들어 있어, 파일 내용을 그대로 붙여 넣거나 첨부하면 됩니다."
    )
    payload = build_ai_export(res)
    md_text = render_ai_markdown(payload, include_prompt=True)
    json_text = json.dumps({"AI 요청 프롬프트": AI_PROMPT, **payload}, ensure_ascii=False, indent=2)
    stamp = f"{res['analysis_start']:%Y%m%d}_{res['analysis_end']:%Y%m%d}"

    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "📝 AI용 리포트 (Markdown, 프롬프트 포함)", data=md_text.encode("utf-8"),
            file_name=f"백테스트_AI분석용_{stamp}.md", mime="text/markdown",
            use_container_width=True, key="dl_ai_md",
        )
    with c2:
        st.download_button(
            "🧾 AI용 데이터 (JSON)", data=json_text.encode("utf-8"),
            file_name=f"백테스트_AI분석용_{stamp}.json", mime="application/json",
            use_container_width=True, key="dl_ai_json",
        )
    st.caption(f"포함 내용: 설정 · 핵심 지표 · 성과 기여도 · 종목별 기여도 · 연도별/월별 수익률 · 주요 낙폭 구간 · "
               f"헤지 금리 · 검증 체크포인트(종가·환율) · 가정 및 한계  |  Markdown 약 {len(md_text):,}자")

    with st.expander("📋 AI 요청 프롬프트 (복사용)", expanded=False):
        st.code(AI_PROMPT, language=None)
    with st.expander("👀 내보낼 데이터 미리보기 (Markdown)", expanded=False):
        st.code(render_ai_markdown(payload, include_prompt=False), language="markdown")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  자산군 내 종목별 수익 기여도 (화면)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTRIB_COLS = ["현지수익 기여(%p)", "환차익 기여(%p)", "헤지손익 기여(%p)", "합계 기여(%p)"]


def contribution_by_class_table(ad: pd.DataFrame) -> pd.DataFrame:
    """자산군별로 묶은 종목 기여도 표 (자산군 소계 행 포함)."""
    rows = []
    for cls, g in ad.groupby("자산군", sort=False):
        cls_total = float(g["합계 기여(%p)"].sum())
        for _, r in g.iterrows():
            rows.append({
                "자산군": cls, "종목": r["종목코드"], "종목명": r["종목명"] + r.get("_tag", ""),
                "평균 비중(%)": r["평균 비중(%)"],
                "상장통화 총수익률(%)": r["상장통화 총수익률(%)"],
                **{c: r[c] for c in CONTRIB_COLS},
                "자산군 내 기여 비중(%)": (r["합계 기여(%p)"] / cls_total * 100) if abs(cls_total) > 1e-12 else None,
            })
        rows.append({
            "자산군": cls, "종목": "▶ 소계", "종목명": f"{cls} 합계",
            "평균 비중(%)": float(g["평균 비중(%)"].sum()),
            "상장통화 총수익률(%)": None,
            **{c: float(g[c].sum()) for c in CONTRIB_COLS},
            "자산군 내 기여 비중(%)": 100.0 if abs(cls_total) > 1e-12 else None,
        })
    return pd.DataFrame(rows)


def render_asset_contribution(res: dict, unit_txt: str):
    ad = res.get("asset_detail")
    if ad is None or ad.empty:
        return
    attr = res["attribution"]
    st.subheader("🧩 자산군 내 종목별 수익 기여도")
    st.caption(
        f"단위: **{unit_txt}**. 각 종목의 기여 = 현지수익(가격·이자·배당) + 환차익 + 헤지손익. "
        f"종목 합계 {ad['합계 기여(%p)'].sum():+.2f}%p + 공모주 Alpha {attr['ipo_contrib']:+.2f}%p "
        f"= 합산 실현치 {attr['total_cagr']:.2f}%"
    )

    # 자산군 소계 카드
    cls_sum = ad.groupby("자산군", sort=False)["합계 기여(%p)"].sum()
    cols = st.columns(len(cls_sum))
    for col, (cls, v) in zip(cols, cls_sum.items()):
        n = int((ad["자산군"] == cls).sum())
        col.metric(cls, f"{v:+.2f}%p", delta=f"{n}개 종목", delta_color="off")

    # 종목별 누적 막대 (현지수익 / 환차익 / 헤지손익)
    labels = [f"{r['자산군']} · {r['종목코드']}" for _, r in ad.iterrows()]
    fig = go.Figure()
    for col_name, name, color in [("현지수익 기여(%p)", "현지수익", "#1976D2"),
                                  ("환차익 기여(%p)", "환차익", "#F57C00"),
                                  ("헤지손익 기여(%p)", "헤지손익", "#00838F")]:
        fig.add_trace(go.Bar(y=labels, x=ad[col_name], name=name, orientation="h", marker_color=color))
    fig.add_trace(go.Scatter(
        y=labels, x=ad["합계 기여(%p)"], mode="markers+text", name="합계",
        marker=dict(color="#212121", size=9, symbol="diamond"),
        text=[f"{v:+.2f}" for v in ad["합계 기여(%p)"]], textposition="middle right",
    ))
    fig.update_layout(
        barmode="relative", template="plotly_white", height=max(260, 46 * len(ad) + 80),
        xaxis_title="기여도 (%p)", yaxis=dict(autorange="reversed"),
        legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
        margin=dict(l=10, r=40, t=30, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)

    code_to_t = {t.replace(".KS", ""): t for t in LISTING_DATES}
    tbl = contribution_by_class_table(ad.assign(_tag=ad["종목코드"].map(lambda c: listing_tag(code_to_t.get(c, c)))))
    num_cols = ["평균 비중(%)", "상장통화 총수익률(%)", *CONTRIB_COLS, "자산군 내 기여 비중(%)"]
    st.dataframe(
        tbl.style.format({c: "{:+.2f}" if "기여(%p)" in c else "{:.2f}" for c in num_cols}, na_rep="-")
           .apply(lambda r: ["font-weight: bold; background-color: #f1f3f5" if r["종목"] == "▶ 소계" else "" for _ in r], axis=1),
        hide_index=True, use_container_width=True,
    )
    st.caption(
        "· 자산군 소계의 **현지수익** 합은 위 ①국채·②지수·⑤금·현금성 기여도와, **환차익** 합은 ③, **헤지손익** 합은 ⑥과 같습니다.  \n"
        "· 상장통화 총수익률은 종목 자체의 기간 수익률(분배 재투자)이고, 기여도는 비중과 시점을 반영한 값입니다. "
        "TAA로 비중이 바뀐 기간이 있으면 두 값의 크기가 다르게 보일 수 있습니다.  \n"
        "· 자산군 내 기여 비중은 종목 기여 ÷ 자산군 소계입니다. 한 자산군 안에 플러스·마이너스 종목이 섞이면 "
        "100%를 넘거나 음수가 될 수 있습니다."
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  종목별 RAW 데이터 엑셀
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RAW_COLUMN_GUIDE = [
    ("분석일", "백테스트 캘린더의 날짜 (한국 종목이 있으면 한국 영업일)"),
    ("원자료 기준일", "그 분석일에 실제로 쓰인 Yahoo Finance 원자료의 날짜. 미국 종목은 한국 영업일 기준 직전 미국 거래일일 수 있음"),
    ("종가(분할 반영, 원자료)", "Yahoo Finance 종가 (분할만 반영, 분배 미반영)"),
    ("분배금(직전 행 이후 합계, 1주당)", "직전 분석일의 원자료 기준일 다음 날 ~ 이번 원자료 기준일 사이의 분배금 합계"),
    ("합성 NAV(은대)", "은대 연 2.53%를 달력일(ACT/365)로 일할한 합성 가격"),
    ("총수익지수", "분배금을 재투자한 총수익 지수 (분석 시작일 = 100)"),
    ("일간 총수익률(상장통화, %)", "총수익지수의 전일 대비 변동률 (달러 자산은 달러 기준)"),
    ("USD/KRW · 환율 변동(%)", "Yahoo Finance KRW=X, 분석일 기준 as-of 값과 전일 대비 변동률"),
    ("환헤지 비율(%)", "해당 종목에 적용한 환헤지 비율 (미국 국고채 / 미국 지수 ETF 각각 설정, 금은 환오픈)"),
    ("현지수익 · 환효과 · 헤지손익(%)", "원화 환산 수익률을 세 요소로 분해한 값 (세 값의 합 = 원화 환산 수익률)"),
    ("원화 환산 수익률(%)", "원화 투자자 기준 당일 수익률 (헤지 반영)"),
    ("적용 비중(%)", "그날 수익률에 적용한 포트폴리오 비중 (TAA 적용일에는 조정된 비중)"),
    ("포트폴리오 기여(당일, %p)", "적용 비중 × 원화 환산 수익률. 모든 종목 합계 + 공모주 Alpha = 포트폴리오 일간 수익률"),
]


def _sheet_name(name: str, used: set) -> str:
    bad = '[]:*?/\\'
    base = "".join("_" if ch in bad else ch for ch in name)[:31]
    out, i = base, 2
    while out in used:
        suffix = f"_{i}"
        out = base[:31 - len(suffix)] + suffix
        i += 1
    used.add(out)
    return out


def build_raw_excel(res: dict) -> bytes:
    """종목별 RAW 데이터 엑셀 (종목마다 시트 1개 + 포트폴리오 + 환율·금리 + 설명)."""
    from openpyxl.utils import get_column_letter

    buf = io.BytesIO()
    used: set = set()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        info = pd.DataFrame(
            [("분석 구간", f"{res['analysis_start']:%Y-%m-%d} ~ {res['analysis_end']:%Y-%m-%d} "
                         f"({res['trading_days']}영업일, {res.get('calendar_label', '-')})"),
             ("환헤지", f"{res.get('hedge_label', '-')} (포트폴리오 기준 {res.get('hedged_share', 0):.1f}%)"),
             ("헤지 금리 출처", res.get("rate_note", "-")),
             ("데이터 출처", "시세·분배금·환율: Yahoo Finance (yfinance) / 금리: ^IRX, FRED"),
             ("", ""), ("[열 설명]", "")] + RAW_COLUMN_GUIDE,
            columns=["항목", "설명"],
        )
        info.to_excel(w, sheet_name=_sheet_name("설명", used), index=False)
        res["weight_table"].to_excel(w, sheet_name=_sheet_name("종목별비중", used), index=False)
        res["asset_detail"].to_excel(w, sheet_name=_sheet_name("종목별기여도", used), index=False)
        res["raw_portfolio"].reset_index().to_excel(w, sheet_name=_sheet_name("포트폴리오", used), index=False)
        if not res["raw_fx_rates"].empty and len(res["raw_fx_rates"].columns):
            res["raw_fx_rates"].reset_index().to_excel(w, sheet_name=_sheet_name("환율·금리", used), index=False)
        for t, df in res["raw_sheets"].items():
            out = df.reset_index()
            out["분석일"] = pd.to_datetime(out["분석일"]).dt.date
            out.to_excel(w, sheet_name=_sheet_name(t.replace(".KS", "").replace(".KQ", ""), used), index=False)

        for ws in w.book.worksheets:
            ws.freeze_panes = "B2"
            for i, col in enumerate(ws.iter_cols(min_row=1, max_row=1), start=1):
                header = str(col[0].value or "")
                width = 60 if ws.title == "설명" and i == 2 else max(11, min(32, len(header) * 1.6 + 2))
                ws.column_dimensions[get_column_letter(i)].width = width
    return buf.getvalue()


def render_raw_download(res: dict):
    """RAW 엑셀은 크기가 커서 버튼을 눌렀을 때만 만들고, 같은 결과에 대해서는 다시 쓰지 않음."""
    run_id = res.get("run_id", "")
    ss = st.session_state
    n_t = len(res.get("raw_sheets", {}))
    n_rows = len(res.get("raw_portfolio", []))
    st.markdown("##### 📦 종목별 RAW 데이터")
    st.caption(f"종목 {n_t}개 × {n_rows:,}일. 종목마다 시트 1개 (원자료 기준일·종가·분배금·총수익지수·환율·헤지비율·"
               f"원화 수익률 분해·적용 비중·당일 기여) + 포트폴리오 · 환율·금리 · 열 설명 시트")
    if ss.get("_raw_xlsx_id") != run_id:
        if st.button("📦 RAW 데이터 엑셀 만들기", use_container_width=True, key="btn_make_raw"):
            with st.spinner("RAW 데이터 엑셀 생성 중..."):
                ss["_raw_xlsx"] = build_raw_excel(res)
                ss["_raw_xlsx_id"] = run_id
    if ss.get("_raw_xlsx_id") == run_id:
        stamp = f"{res['analysis_start']:%Y%m%d}_{res['analysis_end']:%Y%m%d}"
        st.download_button(
            "📥 종목별 RAW 데이터 다운로드 (.xlsx)", data=ss["_raw_xlsx"],
            file_name=f"종목별_RAW데이터_{stamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True, key="dl_raw_xlsx",
        )


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
            help=f"헤지 비율 {res.get('hedge_label', '-')} (포트폴리오 기준 {res.get('hedged_share', 0):.1f}% 헤지) "
                 f"× (원화 − 달러 단기금리). "
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
    render_rate_details(res)

    st.divider()
    render_asset_contribution(res, unit_txt)

    st.divider()

    # ────────────────────────────────────────────────────────────────
    # [3] 시각화 차트 1 & 2
    # ────────────────────────────────────────────────────────────────
    st.subheader("📈 Chart 1 — 누적 자산가치(NAV) 추이")
    fig_nav = go.Figure()
    fig_nav.add_trace(go.Scatter(
        x=res["nav_open"].index, y=res["nav_open"].values,
        name=f"혼합형 펀드 (헤지 {res.get('hedge_label', '-')})",
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
        st.caption(
            f"실제 계산에 쓰인 비중입니다 (데이터가 없어 빠진 종목은 제외 후 재정규화). "
            f"환헤지: {res.get('hedge_label', '-')} → 포트폴리오 기준 {res.get('hedged_share', 0):.1f}% 헤지"
        )
        c_cat, c_asset = st.columns([1, 2])
        with c_cat:
            st.markdown("##### 📌 자산군별 실효 비중")
            cat_df = pd.DataFrame([
                {"자산군": k, "비중(%)": f"{v * 100:.2f}%"} for k, v in res["category_weights"].items()
            ])
            st.dataframe(cat_df, hide_index=True, use_container_width=True)

        with c_asset:
            st.markdown("##### 📌 개별 종목별 실효 비중")
            st.dataframe(res["weight_table"], hide_index=True, use_container_width=True)

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
        if not res["weight_table"].empty:
            res["weight_table"].to_excel(w, sheet_name="종목별비중", index=False)
        if not res["asset_detail"].empty:
            res["asset_detail"].to_excel(w, sheet_name="종목별기여도", index=False)
        res["monthly_returns"].round(4).reset_index().to_excel(w, sheet_name="월별수익률", index=False)
        top_drawdowns(res["nav_open"]).to_excel(w, sheet_name="주요낙폭구간", index=False)
        if res.get("checkpoints"):
            pd.DataFrame(res["checkpoints"]).to_excel(w, sheet_name="검증체크포인트", index=False)
        rate_sum = rate_summary_df(res)
        if not rate_sum.empty:
            rate_sum.to_excel(w, sheet_name="헤지금리요약", index=False)
            rd_exp = res["rate_daily"].round(4).reset_index()
            rd_exp.columns = ["Date"] + list(res["rate_daily"].columns)
            rd_exp.to_excel(w, sheet_name="헤지금리(일별)", index=False)

    st.download_button(
        label="📥 엑셀 다운로드 (국채_ETF_혼합형펀드_백테스팅_결과.xlsx)",
        data=buf.getvalue(),
        file_name="국채_ETF_혼합형펀드_백테스팅_결과.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    render_raw_download(res)

    # ────────────────────────────────────────────────────────────────
    # [7] AI 해설·검증용 데이터 내보내기
    # ────────────────────────────────────────────────────────────────
    st.divider()
    render_ai_export_section(res)

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
