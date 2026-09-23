import os
import time
import hmac
import hashlib
import base64
import requests
import sqlite3
import pandas as pd
import streamlit.components.v1 as components
from pathlib import Path
from bs4 import BeautifulSoup
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode
from urllib.parse import quote
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
from PIL import Image, ImageEnhance
from io import BytesIO
import zipfile

def get_blog_position(keyword):

    url = "https://m.search.naver.com/search.naver"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.0 Mobile/15E148 Safari/604.1"
        )
    }

    params = {
        "query": keyword
    }

    try:
        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=10
        )

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")

        titles = []

        # 네이버 검색 결과에서 블로그 링크를 찾는다.
        for link in soup.find_all("a", href=True):

            href = link.get("href", "")
            text = link.get_text(" ", strip=True)

            if not text:
                continue

            # 네이버 블로그 링크만 대상으로 한다.
            if "blog.naver.com" not in href:
                continue

            # 너무 짧거나 긴 텍스트는 제외
            if len(text) < 5 or len(text) > 150:
                continue

            # 중복 제목 제거
            if text not in titles:
                titles.append(text)

            # 우선 10개까지만
            if len(titles) >= 10:
                break

        return titles

    except Exception as e:
        print("네이버 블로그 제목 수집 오류:", e)
        return []

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

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Streamlit Cloud에서는 Secrets 사용
try:

    if "NAVER_ACCESS_LICENSE" in st.secrets:
        API_KEY = st.secrets["NAVER_ACCESS_LICENSE"]

    if "NAVER_SECRET_KEY" in st.secrets:
        SECRET_KEY = st.secrets["NAVER_SECRET_KEY"]

    if "NAVER_CUSTOMER_ID" in st.secrets:
        CUSTOMER_ID = st.secrets["NAVER_CUSTOMER_ID"]

except Exception:

    pass

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
# 네이버 모바일 블로그 제목 수집
# =========================

def get_naver_blog_titles(keyword):

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

    try:

        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=10
        )

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        titles = []

        # 네이버 검색 결과 블록
        blocks = soup.select("[data-block-id]")

        for block in blocks:

            block_id = block.get("data-block-id")

            if not block_id:
                continue

            # 블로그 영역 또는 웹 영역만 확인
            if (
                block_id != "review/prs_template_v2_review_blog_rra_mo.ts"
                and block_id != "web/prs_template_v2_web_basic_mo.ts"
            ):
                continue

            # 블로그 링크 찾기
            blog_links = block.select(
                "a[href*='blog.naver.com']"
            )

            for link in blog_links:

                # 제목 후보를 찾는다
                candidates = []

                # 링크 내부의 제목처럼 보이는 요소
                for tag in link.find_all(
                    ["strong", "span", "p", "div"]
                ):

                    text = tag.get_text(
                        " ",
                        strip=True
                    )

                    if text:
                        candidates.append(text)

                # 후보가 없으면 링크 전체 텍스트 사용
                if not candidates:
                    candidates.append(
                        link.get_text(
                            " ",
                            strip=True
                        )
                    )

                # 가장 적절한 제목 후보 선택
                title = None

                for candidate in candidates:

                    # 너무 짧은 텍스트 제외
                    if len(candidate) < 8:
                        continue

                    # 본문처럼 너무 긴 텍스트 제외
                    if len(candidate) > 100:
                        continue

                    # 해시태그 위주의 텍스트 제외
                    if candidate.startswith("#"):
                        continue

                    title = candidate
                    break

                if not title:
                    continue

                # 중복 제거
                if title not in titles:
                    titles.append(title)

                # 10개 수집
                if len(titles) >= 10:
                    return titles[:10]

        return titles[:10]

    except Exception as e:

        print(
            "네이버 블로그 제목 수집 오류:",
            e
        )

        return []

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

    keyword = keyword.strip()

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

# =========================
# BlogPilot 대표 배너
# =========================

banner_path = (
    Path(__file__).parent
    / "assets"
    / "blogpilot_banner.png"
)

if banner_path.exists():

    st.image(
        str(banner_path),
        use_container_width=True
    )

st.write("")

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

with st.form("keyword_analysis_form"):

    keyword = st.text_input(
        "검색할 키워드를 입력하세요",
        placeholder="예: 심근경색"
    )

    analyze_button = st.form_submit_button(
        "키워드 분석",
        type="primary"
    )

if analyze_button:

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

                for row in rows[:5]:

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
                for row in rows[5:]:

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
# 저장된 키워드 전체 업데이트
# =========================

def update_all_keywords():

    keywords = load_saved_keywords()

    if not keywords:

        st.warning(
            "업데이트할 키워드가 없습니다."
        )

        return

    updated_count = 0

    progress_bar = st.progress(0)

    status_text = st.empty()

    total = len(keywords)

    for index, item in enumerate(keywords):

        keyword = item["키워드"]

        status_text.write(
            f"🔄 업데이트 중: {keyword}"
        )

        # 네이버 검색량 가져오기
        data = get_keyword_data(keyword)

        if data:

            keyword_data = None

            for result in data.get(
                "keywordList",
                []
            ):

                if result.get(
                    "relKeyword"
                ) == keyword:

                    pc_volume = result.get(
                        "monthlyPcQcCnt",
                        0
                    )

                    mobile_volume = result.get(
                        "monthlyMobileQcCnt",
                        0
                    )

                    try:
                        pc_volume = int(
                            pc_volume
                        )
                    except:
                        pc_volume = 0

                    try:
                        mobile_volume = int(
                            mobile_volume
                        )
                    except:
                        mobile_volume = 0

                    keyword_data = {

                        "키워드": keyword,

                        "월간 검색량":
                            pc_volume + mobile_volume,

                        "PC 검색량":
                            pc_volume,

                        "모바일 검색량":
                            mobile_volume,

                        "경쟁도":
                            result.get(
                                "compIdx",
                                ""
                            ),

                        "PC 클릭률":
                            result.get(
                                "monthlyAvePcCtr",
                                0
                            ),

                        "모바일 클릭률":
                            result.get(
                                "monthlyAveMobileCtr",
                                0
                            )
                    }

                    break

            # 검색량 데이터를 찾았다면 저장
            if keyword_data:

                # 블로그 노출 위치 다시 확인
                blog_result = get_blog_position(
                    keyword
                )

                if blog_result:

                    keyword_data[
                        "블로그 노출 위치"
                    ] = blog_result["위치"]

                else:

                    keyword_data[
                        "블로그 노출 위치"
                    ] = None

                # 최신 데이터 저장
                save_keyword(
                    keyword_data
                )

                # 검색량 기록
                save_keyword_history(
                    keyword,
                    keyword_data[
                        "월간 검색량"
                    ]
                )

                updated_count += 1

        # 진행률
        progress_bar.progress(
            (index + 1) / total
        )

        # 너무 빠르게 요청하지 않도록 잠시 대기
        time.sleep(0.3)

    status_text.success(
        f"✅ {updated_count}개 키워드 업데이트 완료!"
    )

    # 화면에 최신 데이터 반영
    st.session_state.saved_keywords = (
        load_saved_keywords()
    )


# =========================
# 키워드 삭제
# =========================

def delete_keywords(keywords):

    conn = sqlite3.connect(DB_NAME)

    cursor = conn.cursor()

    for keyword in keywords:

        cursor.execute(
            """
            DELETE FROM saved_keywords
            WHERE keyword = ?
            """,
            (keyword,)
        )

        cursor.execute(
            """
            DELETE FROM keyword_history
            WHERE keyword = ?
            """,
            (keyword,)
        )

    conn.commit()

    conn.close()


# =========================
# 키워드 상세 팝업
# =========================

@st.dialog("📊 키워드 상세", width="large")
def show_keyword_detail(selected_keyword):

    st.subheader(selected_keyword)

    # =========================
    # 검색량 추이
    # =========================

    history = load_keyword_history(
        selected_keyword
    )

    if history:

        st.write("### 📈 검색량 추이")

        history_data = []

        for item in history:

            history_data.append({
                "날짜": item["날짜"],
                "검색량": item["검색량"]
            })

        history_df = pd.DataFrame(
            history_data
        )

        st.line_chart(
            history_df,
            x="날짜",
            y="검색량"
        )

    else:

        st.info(
            "아직 검색량 기록이 없습니다."
        )

    # =========================
    # 네이버 모바일 검색
    # =========================

    st.write("### 📱 네이버 모바일 검색")

    encoded_keyword = quote(
        selected_keyword
    )

    naver_url = (
        "https://m.search.naver.com/search.naver"
        "?query="
        + encoded_keyword
    )

    st.link_button(
        "📱 네이버 모바일 검색 열기",
        naver_url,
        use_container_width=True
    )

# =========================
# 키워드 상세 페이지 열기
# =========================

if "keyword_detail" in st.query_params:

    selected_keyword = st.query_params[
        "keyword_detail"
    ]

    show_keyword_detail(
        selected_keyword
    )

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

    df_keywords = pd.DataFrame(
        display_saved_keywords
    )
    df_keywords["clickedKeyword"] = ""
    df_keywords["clickedAt"] = 0

    # =========================
    # 버튼
    # =========================

    button1, button2 = st.columns([1, 1])

    with button1:

        delete_button = st.button(
            "🗑️ 선택 삭제",
            use_container_width=True
        )

    with button2:

        update_button = st.button(
            "🔄 전체 업데이트",
            use_container_width=True
        )

    # =========================
    # 키워드 클릭용 렌더러
    # =========================

    keyword_renderer = JsCode("""
    class KeywordRenderer {

        init(params) {

            this.eGui = document.createElement("a");

            this.eGui.textContent = params.value;

            this.eGui.style.color = "#1a73e8";
            this.eGui.style.textDecoration = "underline";
            this.eGui.style.cursor = "pointer";

            this.eGui.onclick = function(event) {

                event.preventDefault();
                event.stopPropagation();

                params.node.setDataValue(
                    "clickedKeyword",
                    params.value
                );

                params.node.setDataValue(
                    "clickedAt",
                    Date.now()
                );
            };
        }

        getGui() {

            return this.eGui;
        }
    }
    """)
    
    # =========================
    # Excel 스타일 표 설정
    # =========================

    gb = GridOptionsBuilder.from_dataframe(
        df_keywords
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
        headerClass="center-header",
        cellRenderer=keyword_renderer,
        checkboxSelection=True,
        headerCheckboxSelection=True
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

    gb.configure_selection(
        selection_mode="multiple",
        use_checkbox=True,
        suppressRowClickSelection=True
    )

    # 내부용 클릭 데이터
    gb.configure_column(
        "clickedKeyword",
        hide=True,
        suppressColumnsToolPanel=True
    )

    gb.configure_column(
        "clickedAt",
        hide=True,
        suppressColumnsToolPanel=True
    )

    grid_options = gb.build()

    # =========================
    # 헤더 가운데 정렬
    # =========================

    st.markdown("""
    <style>
    .center-header .ag-header-cell-label {
        justify-content: center !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # =========================
    # 표 표시
    # =========================

    grid_response = AgGrid(
        df_keywords,
        gridOptions=grid_options,
        height=400,
        width="100%",
        fit_columns_on_grid_load=True,
        allow_unsafe_jscode=True,
        update_on=[
            "selectionChanged",
            "cellValueChanged"
        ]
    )

    # =========================
    # 키워드 클릭 감지
    # =========================

    clicked_data = grid_response.get("data")

    if clicked_data is not None:

        clicked_df = pd.DataFrame(
            clicked_data
        )

        if (
            "clickedKeyword" in clicked_df.columns
            and "clickedAt" in clicked_df.columns
        ):

            clicked_rows = clicked_df[
                clicked_df["clickedAt"] > 0
            ]

            if not clicked_rows.empty:

                clicked_row = clicked_rows.iloc[
                    clicked_rows["clickedAt"].argmax()
                ]

                clicked_keyword = clicked_row[
                    "clickedKeyword"
                ]

                clicked_time = clicked_row[
                    "clickedAt"
                ]

                if (
                    "last_clicked_time"
                    not in st.session_state
                ):

                    st.session_state.last_clicked_time = 0

                if (
                    clicked_time
                    > st.session_state.last_clicked_time
                ):

                    st.session_state.last_clicked_time = (
                        clicked_time
                    )

                    show_keyword_detail(
                        clicked_keyword
                    )

    # =========================
    # 선택된 키워드
    # =========================

    selected_rows = grid_response.get(
        "selected_rows"
    )

    if selected_rows is not None:

        if len(selected_rows) > 0:

            selected_keywords = (
                selected_rows["키워드"].tolist()
            )

        else:

            selected_keywords = []

    else:

        selected_keywords = []

    # =========================
    # 선택 삭제
    # =========================

    if delete_button:

        if selected_keywords:

            delete_keywords(
                selected_keywords
            )

            st.session_state.saved_keywords = (
                load_saved_keywords()
            )

            st.success(
                f"{len(selected_keywords)}개의 키워드를 삭제했습니다."
            )

            st.rerun()

        else:

            st.warning(
                "삭제할 키워드를 선택해주세요."
            )

    # =========================
    # 전체 업데이트
    # =========================

    if update_button:

        update_all_keywords()

        st.rerun()

else:

    st.info(
        "저장된 키워드가 없습니다."
    )




# =========================
# 블로그 작성 준비
# =========================

st.header("📝 블로그 작성 준비")


saved_keywords = [
    item["키워드"]
    for item in st.session_state.saved_keywords
]


if saved_keywords:

    selected_ai_keyword = st.selectbox(
        "작성할 키워드를 선택하세요",
        saved_keywords
    )


    # =========================
    # 네이버 상위 블로그 제목 확인
    # =========================

    if st.button(
        "🔎 네이버 상위 블로그 제목 확인",
        use_container_width=True
    ):

        naver_titles = get_naver_blog_titles(
            selected_ai_keyword
        )


        if naver_titles:

            # 다른 버튼을 눌러도 유지되도록 저장
            st.session_state.naver_blog_titles = (
                naver_titles
            )

            # 현재 선택된 키워드도 저장
            st.session_state.naver_blog_keyword = (
                selected_ai_keyword
            )

        else:

            st.warning(
                "네이버 블로그 제목을 찾지 못했습니다."
            )


    # =========================
    # 네이버 블로그 제목 표시
    # =========================

    if "naver_blog_titles" in st.session_state:

        naver_titles = (
            st.session_state.naver_blog_titles
        )

        naver_blog_keyword = (
            st.session_state.get(
                "naver_blog_keyword",
                selected_ai_keyword
            )
        )


        st.write("### 📱 네이버 블로그 제목")


        for i, title in enumerate(
            naver_titles,
            1
        ):

            st.write(
                f"{i}. {title}"
            )


        # =========================
        # ChatGPT에 전달할 자료
        # =========================

        chatgpt_text = f"""
        너는 네이버 블로그 글을 작성하는 전문 콘텐츠 에디터다.

        이번 글의 핵심 키워드는 다음과 같다.

        [핵심 키워드]
        {naver_blog_keyword}


        아래는 현재 네이버 모바일 검색에서 확인한
        상위 블로그 제목들이다.

        [네이버 상위 블로그 제목]
        """


        for i, title in enumerate(
            naver_titles,
            1
        ):

            chatgpt_text += (
                f"{i}. {title}\n"
            )


        chatgpt_text += """

        위 검색 결과를 참고해서 아래 순서대로 작업해줘.

        ━━━━━━━━━━━━━━━━━━━━
        1단계. 검색 의도 분석
        ━━━━━━━━━━━━━━━━━━━━

        상위 블로그 제목들을 보고
        이 키워드를 검색하는 사람들이
        무엇을 알고 싶어 하는지 분석해줘.

        단순히 제목을 따라 하지 말고
        검색 결과에서 공통적으로 나타나는
        관심사와 정보 요구를 파악해줘.


        ━━━━━━━━━━━━━━━━━━━━
        2단계. 블로그 제목 제안
        ━━━━━━━━━━━━━━━━━━━━

        검색 의도를 바탕으로
        새로운 블로그 제목 3개를 제안해줘.

        조건:
        - 기존 네이버 제목을 그대로 복사하지 않는다.
        - 기존 제목의 단어만 일부 바꾸는 방식도 피한다.
        - 핵심 키워드를 자연스럽게 포함한다.
        - 실제 검색자가 궁금해할 만한 내용을 담는다.
        - 과장되거나 지나치게 자극적인 표현은 피한다.
        - 서로 다른 방향의 제목을 제안한다.


        ━━━━━━━━━━━━━━━━━━━━
        3단계. 제목 선택
        ━━━━━━━━━━━━━━━━━━━━

        제목 3개를 보여준 다음
        내가 하나를 선택할 수 있도록 기다려줘.

        내가 제목을 선택하면
        그 제목을 기준으로 다음 단계로 진행한다.


        ━━━━━━━━━━━━━━━━━━━━
        4단계. 블로그 글 작성
        ━━━━━━━━━━━━━━━━━━━━

        선택한 제목을 기준으로
        해당 제목을 바탕으로 네이버 블로그에 바로 올릴 수 있는 정보성 글을 작성해줘.


        작성 조건은 다음과 같아.

        1. 전체 분량은 공백 포함 약 1,200~1,500자 정도로 작성해줘.

        2. 네이버 블로그에서 일반인이 읽기 편하도록 너무 전문적인 표현은 피하고, 어려운 의학용어가 나오면 쉽게 풀어서 설명해줘.

        3. 글의 첫 부분에는 독자가 궁금해할 만한 내용을 짧게 짚어주는 서론을 작성해줘. 처음 3~5문장 안에 "이 글에서 무엇을 알 수 있는지" 자연스럽게 알려줘.

        4. 서론 다음에는 반드시 핵심 포인트를 3가지 정도 간단하게 정리해줘.
        예:
        💬 핵심 포인트 미리 보기
        1️⃣ ○○
        2️⃣ ○○
        3️⃣ ○○

        5. 본문은 반드시 아래 형식으로 작성해줘.

        6. 첫 번째 핵심 내용
        내용을 2~4개의 짧은 문단으로 설명

        7. 두 번째 핵심 내용
        내용을 2~4개의 짧은 문단으로 설명

        8. 세 번째 핵심 내용
        내용을 2~4개의 짧은 문단으로 설명

        각 소제목은 독자가 궁금증을 느낄 수 있도록 자연스럽고 쉬운 문장으로 작성해줘.

        6. 본문 중간중간에는 필요한 경우 ✅, 👉, 💡, ⚠️ 등의 이모지를 적절하게 사용해 가독성을 높여줘. 단, 이모지를 과도하게 사용하지 말고 정보 전달에 도움이 되는 곳에만 사용해줘.

        7. 한 문단을 너무 길게 만들지 말고, 모바일에서 읽기 편하도록 2~4문장마다 줄바꿈해줘.

        8. 건강정보이므로 확인되지 않은 내용을 사실처럼 단정하지 마. 의학적으로 근거가 부족하거나 개인차가 큰 내용은 "도움이 될 수 있습니다", "가능성이 있습니다", "사람에 따라 다를 수 있습니다"처럼 표현해줘.

        9. 특정 질환이나 증상을 설명할 때는 단순히 원인만 나열하지 말고,
        ① 왜 그런 증상이 나타날 수 있는지
        ② 일상에서 어떤 상황에서 더 잘 나타나는지
        ③ 스스로 관리할 수 있는 방법은 무엇인지
        ④ 병원 진료가 필요한 경우는 언제인지
        중 필요한 내용을 자연스럽게 포함해줘.

        10. 건강검진이나 질병, 약물, 치료와 관련된 내용에서는 불필요하게 공포감을 조성하지 말고 균형 있게 설명해줘.

        11. 독자가 실제 생활에서 바로 적용할 수 있는 팁을 2~4개 정도 포함해줘.

        12. 글 마지막에는 반드시 다음 형식으로 3줄 요약을 작성해줘.

        🎯 오늘 포스팅 세 줄 요약

        1. ○○

        2. ○○

        3. ○○

        글 전체는 광고문처럼 과장하지 말고, "친근한 건강정보 블로그" 느낌으로 작성해줘.

        9. 독자에게 말을 거는 듯한 자연스러운 표현을 적절히 사용하되, 지나치게 가볍거나 장난스러운 표현은 피하고 신뢰감은 유지해줘.

        10. 제목에 포함된 핵심 키워드는 본문에서 억지스럽지 않게 여러 번 활용하되, 같은 키워드를 과도하게 반복하지 마.

        11. 결론에서 새로운 정보를 갑자기 추가하지 말고, 본문에서 설명한 내용을 자연스럽게 정리해줘.

        중요:

        - 실제 의학적 사실과 일반적인 생활 건강정보를 구분해서 작성할 것
        - 근거가 불확실한 민간요법은 추천하지 말 것
        - 특정 제품이나 병원을 불필요하게 홍보하지 말 것
        - 독자가 오해할 수 있는 표현은 피할 것
        - "무조건", "100%", "완치" 같은 단정적인 표현은 가급적 사용하지 말 것
        - 건강정보 특성상 진료가 필요한 상황이 있다면 자연스럽게 안내할 것

        최종 결과는 설명이나 작성 과정 없이, 완성된 네이버 블로그 글부터 바로 보여줘.


        ━━━━━━━━━━━━━━━━━━━━
        5단계. 이미지 검색어 6개
        ━━━━━━━━━━━━━━━━━━━━

        마지막으로 글에 사용할 만한 이미지 6개를 선정하고, 이미지 생성이나 검색에 바로 복사해서 사용할 수 있도록 영어 키워드 또는 짧은 영어 문장으로 작성해줘.

        예:
        📷 Image Keywords

        person checking oral health in front of mirror
        close-up of healthy tongue
        drinking water for hydration
        using a tongue scraper
        dental hygiene routine
        dentist examining patient's mouth

        이미지 키워드는 본문과 실제로 관련된 장면을 선정하고, 추상적인 표현보다는 사진이나 일러스트로 만들기 쉬운 구체적인 장면을 사용해줘.
        """


        # =========================
        # 화면 표시
        # =========================

        st.write("### 📋 ChatGPT에 전달할 자료")


        st.code(
            chatgpt_text,
            language=None
        )


        st.info(
            "위 내용을 복사해서 ChatGPT 블로그 프로젝트에 "
            "붙여넣으세요. 제목 선정 → 글 작성 → 이미지 검색어 6개 "
            "생성까지 이어서 진행할 수 있습니다."
        )


        # =========================
        # 복사용 텍스트
        # =========================

        st.write("### 📋 ChatGPT에 전달할 자료")


        st.code(
            chatgpt_text,
            language=None
        )


        st.info(
            "위 내용을 복사해서 ChatGPT 블로그 프로젝트에 "
            "붙여넣어 제목 선정과 글 작성을 진행하세요."
        )


else:

    st.info(
        "먼저 키워드 분석에서 키워드를 저장해주세요."
    )

# =========================
# 이미지 검색
# =========================

st.header("📷 이미지 검색")


image_queries_text = st.text_area(
    "이미지 검색어를 입력하세요",
    placeholder=(
        "예:\n"
        "심근경색 심장 혈관 막힘\n"
        "심근경색 가슴 통증\n"
        "관상동맥 심장 구조\n"
        "심근경색 응급상황\n"
        "심근경색 예방 생활습관\n"
        "심혈관 건강 식단"
    ),
    height=180
)


# =========================
# Google 이미지 검색 함수
# =========================

def search_google_images(query, num_results=6):

    url = "https://serpapi.com/search.json"

    params = {
        "engine": "google_images",
        "q": query,
        "api_key": SERPAPI_KEY,
        "ijn": "0"
    }

    try:

        response = requests.get(
            url,
            params=params,
            timeout=15
        )

        if response.status_code != 200:

            print(
                "SerpApi 오류:",
                response.status_code,
                response.text
            )

            return []

        data = response.json()

        return data.get(
            "images_results",
            []
        )[:num_results]

    except Exception as e:

        print(
            "이미지 검색 오류:",
            e
        )

        return []


# =========================
# 세션 상태
# =========================

if "image_queries" not in st.session_state:

    st.session_state.image_queries = []


if "image_results" not in st.session_state:

    st.session_state.image_results = {}


if "selected_images" not in st.session_state:

    st.session_state.selected_images = []


# =========================
# 이미지 검색
# =========================

if st.button(
    "🔎 이미지 검색",
    use_container_width=True
):

    # =========================
    # 이미지 검색어 정리
    # =========================

    import re


    image_queries = []

    for line in image_queries_text.split("\n"):

        line = line.strip()

        if not line:
            continue

        # -------------------------
        # 앞의 번호 제거
        # 예:
        # 1. headache patient
        # 2) stroke symptoms
        # 3. "brain illustration"
        # -------------------------

        line = re.sub(
            r"^\d+[\.\)]\s*",
            "",
            line
        )

        # -------------------------
        # 앞뒤 따옴표 제거
        # -------------------------

        line = line.strip(
            "\"'“”‘’"
        )

        # -------------------------
        # 다시 공백 정리
        # -------------------------

        line = line.strip()

        if line:
            image_queries.append(line)


    if not image_queries:

        st.warning(
            "이미지 검색어를 입력해주세요."
        )


    elif len(image_queries) > 6:

        st.warning(
            "이미지 검색어는 최대 6개까지 입력할 수 있습니다."
        )


    else:

        # 새 검색이므로 기존 결과 초기화
        st.session_state.image_queries = (
            image_queries
        )

        st.session_state.image_results = {}

        st.session_state.selected_images = []


        progress = st.progress(0)

        status_text = st.empty()

        total_queries = len(
            image_queries
        )


        # -------------------------
        # SerpApi 실제 검색
        # -------------------------

        for index, query in enumerate(
            image_queries
        ):

            status_text.write(
                f"🔎 이미지 검색 중: {query}"
            )


            results = search_google_images(
                query,
                num_results=6
            )


            # 검색 결과 저장
            st.session_state.image_results[
                query
            ] = results


            progress.progress(
                (index + 1) /
                total_queries
            )


        progress.empty()


        status_text.success(
            f"✅ {total_queries}개 검색어의 이미지 검색이 완료되었습니다."
        )


# =========================
# 검색 결과 표시
# =========================
#
# 중요:
# 여기서는 "선택"만 한다.
# 편집 코드는 이 아래에 있다.
# =========================

if st.session_state.image_results:

    st.write("### 🖼️ 이미지 선택")

    st.caption(
        "사용할 이미지를 최대 6개까지 선택해주세요."
    )


    for query_index, query in enumerate(
        st.session_state.image_queries
    ):

        results = (
            st.session_state
            .image_results
            .get(query, [])
        )


        if not results:

            st.warning(
                f"'{query}' 검색 결과가 없습니다."
            )

            continue


        st.write(
            f"#### 🔎 {query}"
        )


        # =========================
        # 검색 결과 이미지
        # =========================

        cols = st.columns(6)


        for image_index, image in enumerate(
            results[:6]
        ):

            with cols[image_index]:

                thumbnail = image.get(
                    "thumbnail"
                )


                if thumbnail:

                    st.image(
                        thumbnail,
                        use_container_width=True
                    )


                title = image.get(
                    "title",
                    "제목 없음"
                )


                # -------------------------
                # 이미지 고유 ID
                # -------------------------

                image_id = (
                    f"{query_index}_"
                    f"{image_index}"
                )


                # -------------------------
                # 현재 선택 여부
                # -------------------------

                is_selected = any(
                    item["id"] == image_id
                    for item
                    in st.session_state.selected_images
                )


                checked = st.checkbox(
                    "선택",
                    value=is_selected,
                    key=f"select_{image_id}"
                )


                # -------------------------
                # 이미지 선택
                # -------------------------

                if checked and not is_selected:

                    # 최대 6개
                    if len(
                        st.session_state.selected_images
                    ) >= 6:

                        st.warning(
                            "이미지는 최대 6개까지 선택할 수 있습니다."
                        )

                    else:

                        st.session_state.selected_images.append({

                            "id": image_id,

                            "query": query,

                            "title": title,

                            "thumbnail": thumbnail,

                            "original": image.get(
                                "original",
                                ""
                            ),

                            "link": image.get(
                                "link",
                                ""
                            )
                        })


                # -------------------------
                # 선택 해제
                # -------------------------

                elif (
                    not checked
                    and is_selected
                ):

                    st.session_state.selected_images = [

                        item

                        for item
                        in st.session_state.selected_images

                        if item["id"] != image_id
                    ]


        st.divider()


# =========================================================
# 여기까지가 "이미지 선택"
#
# 아래부터는 검색 결과가 모두 끝난 뒤 나오는
# "선택한 이미지 편집"
# =========================================================


selected_count = len(
    st.session_state.selected_images
)


st.write(
    f"### ✂️ 선택한 이미지 편집 ({selected_count}개)"
)


if selected_count == 0:

    st.info(
        "위의 검색 결과에서 이미지를 선택해주세요."
    )


else:

    edited_images = []


    # =========================
    # 선택된 이미지 편집
    # =========================

    for image_index, selected_image in enumerate(
        st.session_state.selected_images
    ):

        st.write(
            f"#### 🖼️ 이미지 {image_index + 1}"
        )


        image_url = selected_image.get(
            "original"
        )


        if not image_url:

            image_url = selected_image.get(
                "thumbnail"
            )


        try:

            # =========================
            # 원본 이미지 가져오기
            # =========================

            response = requests.get(
                image_url,
                timeout=15,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 "
                        "(Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 "
                        "(KHTML, like Gecko) "
                        "Chrome/140.0 Safari/537.36"
                    )
                }
            )


            response.raise_for_status()


            original_image = Image.open(
                BytesIO(
                    response.content
                )
            ).convert("RGB")


            # =========================
            # 원본 크기
            # =========================

            st.caption(
                f"원본 크기: "
                f"{original_image.width} × "
                f"{original_image.height}px"
            )


            # =========================
            # 940 × 520 비율
            # =========================

            target_ratio = 940 / 520


            original_ratio = (
                original_image.width /
                original_image.height
            )


            if original_ratio > target_ratio:

                crop_height = (
                    original_image.height
                )

                crop_width = int(
                    crop_height *
                    target_ratio
                )


            else:

                crop_width = (
                    original_image.width
                )

                crop_height = int(
                    crop_width /
                    target_ratio
                )


            # =========================
            # 이동 가능한 범위
            # =========================

            max_left = (
                original_image.width -
                crop_width
            )


            max_top = (
                original_image.height -
                crop_height
            )


            # =========================
            # 이미지 + 조절 영역
            # =========================

            image_col, control_col = st.columns(
                [1.15, 1]
            )


            # =========================
            # 위치 및 밝기 조절
            # =========================

            with control_col:

                st.write("**✂️ 이미지 조절**")


                # -------------------------
                # 가로 위치
                # -------------------------

                if max_left > 0:

                    horizontal_position = st.slider(
                        "↔️ 가로 위치",
                        0,
                        max_left,
                        max_left // 2,
                        key=f"h_{image_index}"
                    )

                else:

                    horizontal_position = 0


                # -------------------------
                # 세로 위치
                # -------------------------

                if max_top > 0:

                    vertical_position = st.slider(
                        "↕️ 세로 위치",
                        0,
                        max_top,
                        max_top // 2,
                        key=f"v_{image_index}"
                    )

                else:

                    vertical_position = 0


                # -------------------------
                # 밝기
                # -------------------------

                brightness = st.slider(
                    "☀️ 밝기",
                    min_value=1.00,
                    max_value=1.20,
                    value=1.08,
                    step=0.01,
                    key=f"brightness_{image_index}"
                )


                st.caption(
                    "최종 저장 크기: 940 × 520"
                )


            # =========================
            # 크롭
            # =========================

            cropped_image = original_image.crop(
                (
                    horizontal_position,
                    vertical_position,
                    horizontal_position + crop_width,
                    vertical_position + crop_height
                )
            )


            # =========================
            # 940 × 520 리사이즈
            # =========================

            edited_image = cropped_image.resize(
                (940, 520),
                Image.Resampling.LANCZOS
            )


            # =========================
            # 밝기 적용
            # =========================

            edited_image = (
                ImageEnhance.Brightness(
                    edited_image
                ).enhance(brightness)
            )


            # =========================
            # 미리보기
            # =========================

            with image_col:

                st.image(
                    edited_image,
                    caption="940 × 520",
                    width=420
                )


            # =========================
            # JPEG 생성
            # =========================

            output = BytesIO()


            edited_image.save(
                output,
                format="JPEG",
                quality=95,
                optimize=True
            )


            output.seek(0)


            edited_images.append({
                "index": image_index + 1,
                "data": output.getvalue()
            })


        except Exception as e:

            st.error(
                f"이미지 {image_index + 1} "
                f"처리 오류: {e}"
            )


        st.divider()


    # =========================
    # ZIP 다운로드
    # =========================

    if edited_images:

        # -------------------------
        # 키워드 파일명 정리
        # -------------------------

        safe_keyword = "".join(
            c
            for c in selected_ai_keyword
            if c not in r'\/:*?"<>|'
        ).strip()


        # -------------------------
        # ZIP 생성
        # -------------------------

        zip_buffer = BytesIO()


        with zipfile.ZipFile(
            zip_buffer,
            "w",
            zipfile.ZIP_DEFLATED
        ) as zip_file:

            for image in edited_images:

                filename = (
                    f"{safe_keyword}_"
                    f"{image['index']:02d}.jpg"
                )


                zip_file.writestr(
                    filename,
                    image["data"]
                )


        zip_buffer.seek(0)


        # =========================
        # 다운로드
        # =========================

        st.write(
            f"### 📦 편집 완료 "
            f"({len(edited_images)}개)"
        )


        st.download_button(
            label=(
                f"⬇️ {len(edited_images)}개 "
                f"이미지 한 번에 다운로드"
            ),
            data=zip_buffer.getvalue(),
            file_name=(
                f"{safe_keyword}_이미지.zip"
            ),
            mime="application/zip",
            use_container_width=True
        )