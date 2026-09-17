import os
import time
import hmac
import hashlib
import base64
import requests
import sqlite3
import pandas as pd
from bs4 import BeautifulSoup
from st_aggrid import AgGrid, GridOptionsBuilder

def get_blog_position(keyword):

    url = "https://m.search.naver.com/search.naver"

    params = {
        "query": keyword
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/18.0 Mobile/15E148 Safari/604.1"
        )
    }

    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=10
    )

    if response.status_code != 200:
        return None

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    blocks = soup.select("[data-block-id]")

    position = 0

    # 독립 블로그 영역 확인
    for block in blocks:

        block_id = block.get("data-block-id")

        if not block_id:
            continue

        if "/prs_template_" not in block_id:
            continue

        position += 1

        if block_id == (
            "review/prs_template_v2_review_blog_rra_mo.ts"
        ):

            return {
                "위치": position,
                "형태": "독립 블로그"
            }

    # 웹 영역 안의 블로그 확인
    position = 0

    for block in blocks:

        block_id = block.get("data-block-id")

        if not block_id:
            continue

        if "/prs_template_" not in block_id:
            continue

        position += 1

        if block_id == (
            "web/prs_template_v2_web_basic_mo.ts"
        ):

            blog_links = block.select(
                "a[href*='blog.naver.com']"
            )

            if blog_links:

                return {
                    "위치": position,
                    "형태": "웹 영역 내 블로그"
                }

    print("블로그 못 찾음:", keyword)
    return None

# =========================
# 데이터베이스
# =========================

DB_NAME = "blogpilot.db"


def init_database():
    
    
    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT UNIQUE,
            monthly_volume INTEGER,
            competition TEXT,
            pc_volume INTEGER DEFAULT 0,
            mobile_volume INTEGER DEFAULT 0,
            pc_ctr REAL DEFAULT 0,
            mobile_ctr REAL DEFAULT 0
        )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS keyword_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword TEXT,
        monthly_volume INTEGER,
        recorded_at TEXT
    )
""")

    try:
        cursor.execute(
            "ALTER TABLE saved_keywords ADD COLUMN pc_volume INTEGER DEFAULT 0"
        )
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute(
            "ALTER TABLE saved_keywords ADD COLUMN mobile_volume INTEGER DEFAULT 0"
        )
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute(
            "ALTER TABLE saved_keywords ADD COLUMN pc_ctr REAL DEFAULT 0"
        )
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute(
            "ALTER TABLE saved_keywords ADD COLUMN mobile_ctr REAL DEFAULT 0"
        )
    except sqlite3.OperationalError:
        pass
        # 기존 DB에 새 컬럼 추가

     
    # 블로그 영역 위치     
    try:
        cursor.execute("""
            ALTER TABLE saved_keywords
            ADD COLUMN blog_position INTEGER
        """)
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


init_database()



def save_keyword(keyword_data):

    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO saved_keywords
        (
            keyword,
            monthly_volume,
            competition,
            pc_volume,
            mobile_volume,
            pc_ctr,
            mobile_ctr,
            blog_position
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        keyword_data["키워드"],
        keyword_data["월간 검색량"],
        keyword_data.get("경쟁도", ""),
        keyword_data.get("PC 검색량", 0),
        keyword_data.get("모바일 검색량", 0),
        keyword_data.get("PC 클릭률", 0),
        keyword_data.get("모바일 클릭률", 0),
        keyword_data.get("블로그 노출 위치")
    ))

    conn.commit()

    conn.close()

def load_saved_keywords():

    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            keyword,
            monthly_volume,
            competition,
            pc_volume,
            mobile_volume,
            pc_ctr,
            mobile_ctr,
            blog_position
        FROM saved_keywords
        ORDER BY id DESC
    """)

    results = cursor.fetchall()

    conn.close()

    keywords = []

    for keyword, monthly_volume, competition, pc_volume, mobile_volume, pc_ctr, mobile_ctr, blog_position in results:

        keywords.append({
            "키워드": keyword,
            "월간 검색량": monthly_volume,
            "경쟁도": competition,
            "PC 검색량": pc_volume,
            "모바일 검색량": mobile_volume,
            "PC 클릭률": pc_ctr,
            "모바일 클릭률": mobile_ctr,
            "블로그 노출 위치": blog_position
        })

    return keywords

def save_keyword_history(keyword, monthly_volume):

    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()

    recorded_at = time.strftime("%Y-%m-%d")

    cursor.execute("""
        INSERT INTO keyword_history
        (keyword, monthly_volume, recorded_at)
        VALUES (?, ?, ?)
    """, (
        keyword,
        monthly_volume,
        recorded_at
    ))
    
    conn.commit()
    conn.close()

def load_keyword_history(keyword):

    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()

    cursor.execute("""
        SELECT recorded_at, monthly_volume
        FROM keyword_history
        WHERE keyword = ?
        ORDER BY id ASC
    """, (keyword,))

    results = cursor.fetchall()

    conn.close()

    history = []

    for recorded_at, monthly_volume in results:

        history.append({
            "날짜": recorded_at,
            "검색량": monthly_volume
        })

    return history


import streamlit as st
from dotenv import load_dotenv


# =========================
# 환경설정
# =========================

load_dotenv()

API_KEY = os.getenv("NAVER_ACCESS_LICENSE")
SECRET_KEY = os.getenv("NAVER_SECRET_KEY")
CUSTOMER_ID = os.getenv("NAVER_CUSTOMER_ID")

BASE_URL = "https://api.searchad.naver.com"


# =========================
# Streamlit 기억공간
# =========================

if "saved_keywords" not in st.session_state:
    st.session_state.saved_keywords = []

if "selected_keyword" not in st.session_state:
    st.session_state.selected_keyword = None

if "show_keyword_dialog" not in st.session_state:
    st.session_state.show_keyword_dialog = False

if "keyword_rows" not in st.session_state:
    st.session_state.keyword_rows = []

# =========================
# 모바일 네이버 블로그 노출 위치
# =========================

def get_blog_position(keyword):

    url = "https://m.search.naver.com/search.naver"

    params = {
        "query": keyword
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/18.0 Mobile/15E148 Safari/604.1"
        )
    }

    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=10
    )

    if response.status_code != 200:
        return None

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    blocks = soup.select("[data-block-id]")

    position = 0

    # 독립 블로그 영역 확인
    for block in blocks:

        block_id = block.get("data-block-id")

        if not block_id:
            continue

        if "/prs_template_" not in block_id:
            continue

        position += 1

        if block_id == (
            "review/prs_template_v2_review_blog_rra_mo.ts"
        ):

            return {
                "위치": position,
                "형태": "독립 블로그"
            }

    # 웹 영역 안의 블로그 확인
    position = 0

    for block in blocks:

        block_id = block.get("data-block-id")

        if not block_id:
            continue

        if "/prs_template_" not in block_id:
            continue

        position += 1

        if block_id == (
            "web/prs_template_v2_web_basic_mo.ts"
        ):

            blog_links = block.select(
                "a[href*='blog.naver.com']"
            )

            if blog_links:

                return {
                    "위치": position,
                    "형태": "웹 영역 내 블로그"
                }

    return None

# =========================
# 네이버 API 인증
# =========================

def make_signature(timestamp, method, uri):

    message = f"{timestamp}.{method}.{uri}"

    digest = hmac.new(
        SECRET_KEY.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).digest()

    return base64.b64encode(digest).decode("utf-8")


# =========================
# 네이버 키워드 데이터 가져오기
# =========================

def get_keyword_data(keyword):

    path = "/keywordstool"
    method = "GET"

    params = {
        "hintKeywords": keyword,
        "includeHintKeywords": "1",
        "showDetail": "1"
    }

    timestamp = str(int(time.time() * 1000))

    signature = make_signature(
        timestamp,
        method,
        path
    )

    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Timestamp": timestamp,
        "X-API-KEY": API_KEY,
        "X-Customer": str(CUSTOMER_ID),
        "X-Signature": signature
    }

    response = requests.get(
        BASE_URL + path,
        params=params,
        headers=headers,
        timeout=10
    )

    if response.status_code != 200:

        st.error(
            f"네이버 API 오류: {response.status_code}"
        )

        st.code(response.text)

        return None

    return response.json()


# =========================
# 검색량 숫자로 변환
# =========================

def to_number(value):

    if isinstance(value, (int, float)):
        return int(value)

    if isinstance(value, str):

        if value.startswith("<"):
            return 0

        try:
            return int(value.replace(",", ""))
        except ValueError:
            return 0

    return 0


# =========================
# 화면 설정
# =========================

st.set_page_config(
    page_title="BlogPilot",
    page_icon="📝",
    layout="wide"
)

st.session_state.saved_keywords = load_saved_keywords()

st.title("📝 BlogPilot")

st.write(
    "나만의 블로그 키워드 도우미"
)

st.divider()


# =========================
# 키워드 분석
# =========================

st.header("🔍 키워드 분석")

keyword = st.text_input(
    "검색할 키워드를 입력하세요",
    placeholder="예: 심근경색"
)


if st.button(
    "키워드 분석",
    type="primary"
):

    if not keyword.strip():

        st.warning(
            "키워드를 입력해주세요."
        )

    elif not API_KEY or not SECRET_KEY or not CUSTOMER_ID:

        st.error(
            ".env 파일의 네이버 API 정보를 확인해주세요."
        )

    else:

        with st.spinner(
            "네이버에서 키워드 데이터를 가져오는 중..."
        ):

            data = get_keyword_data(
                keyword.strip()
            )

        if data:

            keyword_list = data.get(
                "keywordList",
                []
            )

            # 입력한 검색어에서 핵심 키워드 추출
            main_keyword = keyword.strip().split()[0]

            # 핵심 키워드가 포함된 연관 키워드만 남김
            keyword_list = [
                item
                for item in keyword_list
                if main_keyword in item.get("relKeyword", "")
            ]

            if not keyword_list:

                st.warning(
                    "검색 결과가 없습니다."
                )

            else:

                rows = []

                for item in keyword_list:

                    pc = to_number(
                        item.get(
                            "monthlyPcQcCnt",
                            0
                        )
                    )

                    mobile = to_number(
                        item.get(
                            "monthlyMobileQcCnt",
                            0
                        )
                    )

                    pc_ctr = item.get(
                        "monthlyAvePcCtr",
                        0
                    )

                    mobile_ctr = item.get(
                        "monthlyAveMobileCtr",
                        0
                    )

                    rows.append({
                        "키워드": item.get(
                            "relKeyword",
                            ""
                        ),
                        "PC 검색량": pc,
                        "모바일 검색량": mobile,
                        "월간 검색량": pc + mobile,
                        "경쟁도": item.get(
                            "compIdx",
                            ""
                        ),
                        "PC 클릭률": pc_ctr,
                        "모바일 클릭률": mobile_ctr
                    })

                rows.sort(
                    key=lambda x: x["월간 검색량"],
                    reverse=True
                )

                rows = rows[:20]

                # =========================
                # 모바일 네이버 블로그 노출 위치 분석
                # =========================

                for row in rows[:20]:

                    blog_result = get_blog_position(
                        row["키워드"]
                    )

                    if blog_result:

                        row["블로그 노출 위치"] = blog_result["위치"]
                        row["블로그 노출 형태"] = blog_result["형태"]

                    else:

                        row["블로그 노출 위치"] = None
                        row["블로그 노출 형태"] = "블로그 없음"


                # 나머지 키워드는 아직 조회하지 않음
                for row in rows[20:]:

                    row["블로그 노출 위치"] = None
                    row["블로그 노출 형태"] = "미조회"


                # 검색 결과를 기억
                st.session_state.keyword_rows = rows


# =========================
# 검색 결과 표시
# =========================

if st.session_state.keyword_rows:

    rows = st.session_state.keyword_rows

    st.success(
        f"{len(rows)}개의 키워드를 찾았습니다."
    )

    top_keyword = rows[0]


    st.subheader(
    "📊 검색량 높은 키워드"
    )

    # 헤더
    header1, header2, header3, header4, header5 = st.columns(
        [3, 2, 1.5, 1.5, 1.2]
    )

    header1.write("키워드")
    header2.write("월간 검색량")
    header3.write("PC")
    header4.write("모바일")
    header5.write("블로그 위치")

    st.divider()

    # 검색 결과 표시
    for row in rows:

        col1, col2, col3, col4, col5 = st.columns(
            [3, 2, 1.5, 1.5, 1.2]
        )

        # 키워드 클릭 → 바로 저장
        if col1.button(
            f"⭐ {row['키워드']}",
            key=f"search_keyword_{row['키워드']}"
        ):

            already_saved = any(
                item["키워드"] == row["키워드"]
                for item in st.session_state.saved_keywords
            )

            if not already_saved:

                save_keyword(row)

                st.session_state.saved_keywords = (
                    load_saved_keywords()
                )

                st.success(
                    f"'{row['키워드']}' 저장 완료!"
                )

            else:

                st.info(
                    "이미 저장된 키워드입니다."
                )

        col2.write(
            f"{row['월간 검색량']:,}"
        )

        col3.write(
            f"{row['PC 검색량']:,}"
        )

        col4.write(
            f"{row['모바일 검색량']:,}"
        )

        blog_position = row.get(
            "블로그 노출 위치"
        )

        if blog_position is not None:
            col5.write(
                str(blog_position)
            )
        else:
            col5.write("-")

    
# =========================
# 내 키워드
# =========================

st.subheader("⭐ 내 키워드")

if st.session_state.saved_keywords:

    display_saved_keywords = []

    for item in st.session_state.saved_keywords:

        display_saved_keywords.append({
            "키워드": item["키워드"],
            "월간 검색량": item["월간 검색량"],
            "PC 검색량": item["PC 검색량"],
            "모바일 검색량": item["모바일 검색량"],
            "블로그 위치": item.get(
                "블로그 노출 위치",
                "-"
            )
        })

    # =========================
    # Excel 스타일 표 설정
    # =========================

    st.markdown("""
    <style>
    .center-header .ag-header-cell-label {
        justify-content: center !important;
    }
    </style>
    """, unsafe_allow_html=True)

    gb = GridOptionsBuilder.from_dataframe(
        pd.DataFrame(display_saved_keywords)
    )

    gb.configure_default_column(
        sortable=True,
        filter=True,
        resizable=True,
        cellStyle={
            "textAlign": "center"
        }
    )

    gb.configure_column(
        "키워드",
        filter="agTextColumnFilter",
        headerClass="center-header"
    )

    gb.configure_column(
        "월간 검색량",
        filter="agNumberColumnFilter",
        headerClass="center-header"
    )

    gb.configure_column(
        "PC 검색량",
        filter="agNumberColumnFilter",
        headerClass="center-header"
    )

    gb.configure_column(
        "모바일 검색량",
        filter="agNumberColumnFilter",
        headerClass="center-header"
    )

    gb.configure_column(
        "블로그 위치",
        filter="agNumberColumnFilter",
        headerClass="center-header"
    )

    # 행 선택
    gb.configure_selection(
        selection_mode="single",
        use_checkbox=False
    )

    grid_options = gb.build()

    # =========================
    # 표 표시
    # =========================

    grid_response = AgGrid(
        pd.DataFrame(display_saved_keywords),
        gridOptions=grid_options,
        height=400,
        width="100%",
        fit_columns_on_grid_load=True,
        allow_unsafe_jscode=False
    )

    # =========================
    # 키워드 선택
    # =========================

    selected_rows = grid_response.get(
        "selected_rows"
    )

    if selected_rows is not None:

        if len(selected_rows) > 0:

            selected_keyword = selected_rows.iloc[0]["키워드"]

            st.session_state.selected_keyword = (
                selected_keyword
            )

            st.session_state.show_keyword_dialog = True

else:

    st.info(
        "아직 저장된 키워드가 없습니다."
    )

# =========================
# AI 블로그 작성
# =========================



st.divider()

st.header(
    "✍️ AI 블로그 작성"
)

st.write(
    "키워드를 선택하면 제목 추천과 "
    "AI 초안 작성을 시작합니다."
)