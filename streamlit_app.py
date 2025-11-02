import streamlit as st
import yaml
import pandas as pd
from app.db import Base, engine, SessionLocal
from app.models import *
from app.news import ingest_rss
from app.financials import load_financials_from_folder
from app.dividends import upsert_dividends_from_csv
from app.screener import screen_fundamental, screen_technical, merge_with_dividends

st.set_page_config(page_title="Economic News & Screener (VN)", layout="wide")

@st.cache_resource
def init_db_and_load():
    Base.metadata.create_all(bind=engine)
    with open("config_cloud.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    with SessionLocal() as s:
        try:
            ingest_rss(s, cfg.get("news_sources", []))
        except Exception as e:
            st.sidebar.warning(f"Không cập nhật RSS: {e}")
        try:
            load_financials_from_folder(s, "data/financials")
        except Exception as e:
            st.sidebar.warning(f"Không nạp BCTC: {e}")
        try:
            upsert_dividends_from_csv(s, "data/dividend_calendar.csv")
        except Exception as e:
            st.sidebar.warning(f"Không nạp cổ tức: {e}")
    return cfg

cfg = init_db_and_load()

st.title("📰 Tin tức & 📈 Stock Screener (VN)")

tab1, tab2 = st.tabs(["Tin kinh tế", "Sàng lọc cổ phiếu"])

with tab1:
    with SessionLocal() as s:
        rows = s.execute(
            "SELECT source, title, link, published_at, summary FROM news ORDER BY published_at DESC NULLS LAST, id DESC LIMIT 60"
        ).fetchall()
        if not rows:
            st.info("Chưa có tin – hãy thử lại sau.")
        for r in rows:
            title = r[1]
            link = r[2]
            src  = r[0]
            pub  = r[3]
            smy  = r[4]
            st.markdown(f"**{title}**")
            st.caption(f"Nguồn: {src}" + (f" – {pub}" if pub else ""))
            if smy:
                st.write(smy)
            st.link_button("Đọc bài", link, use_container_width=False)
            st.divider()

with tab2:
    with SessionLocal() as s:
        fsel = screen_fundamental(s, cfg.get("financial_thresholds", {}))
        try:
            prices = pd.read_csv("data/prices.csv", parse_dates=["date"])
        except FileNotFoundError:
            prices = pd.DataFrame(columns=["date", "symbol", "close", "volume"])
        tsel = screen_technical(prices, cfg.get("screener", {}))
        merged = pd.concat([fsel, tsel], ignore_index=True).drop_duplicates(subset=["symbol"], keep="first")
        final = merge_with_dividends(s, merged)
        st.dataframe(final, use_container_width=True)
        st.caption("Gợi ý chỉ nhằm tham khảo, KHÔNG phải khuyến nghị đầu tư.")
