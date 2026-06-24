import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import time

st.set_page_config(page_title="美股小市值慢牛监控", layout="wide")

st.title("📈 美股小市值慢牛监控工具")
st.markdown("**筛选逻辑**：市值 < 20亿 + 底部缓慢抬升（温和上涨 + 量能配合）")

# ==================== 配置 ====================
if 'results' not in st.session_state:
    st.session_state.results = []

class Config:
    MARKET_CAP_MAX = st.sidebar.slider("最大市值 (亿美元)", 5, 50, 20)
    MIN_UP_DAYS = st.sidebar.slider("至少上涨天数", 8, 25, 12)
    MAX_DRAWDOWN = st.sidebar.slider("最大回撤(%)", 5, 25, 12)
    VOLUME_INCREASE = st.sidebar.slider("量能放大倍数", 1.0, 3.0, 1.4)

# ==================== 数据获取 ====================
@st.cache_data(ttl=3600)
def get_us_small_cap_candidates():
    """获取美股小市值候选（简化，使用知名列表 + 随机补充）"""
    # 常见小市值板块示例，可后续扩展
    tickers = [
        "SOUN", "RKLB", "PLUG", "FCEL", "AEVA", "LUNR", "SERV", "BBAI", 
        "QBTS", "QBTS", "PEGY", "KSCP", "MULN", "HOLO", "PEGY", "GCT"
    ]
    # 可以扩展更多
    return list(set(tickers))

def analyze_slow_bull(ticker):
    try:
        end = datetime.now()
        start = end - timedelta(days=60)
        df = yf.download(ticker, start=start, end=end, progress=False)
        
        if len(df) < 30:
            return None
        
        df['Return'] = df['Close'].pct_change()
        df['MA10'] = df['Close'].rolling(10).mean()
        df['Volume_MA20'] = df['Volume'].rolling(20).mean()
        
        recent = df.tail(25)
        older = df.iloc[-40:-15]  # 底部区间
        
        # 慢牛条件
        total_return = (recent['Close'].iloc[-1] / older['Close'].iloc[0] - 1) * 100
        up_days = (recent['Return'] > 0).sum()
        max_dd = ((recent['Close'] / recent['Close'].cummax()) - 1).min() * 100
        avg_volume_ratio = recent['Volume'].mean() / older['Volume'].mean()
        
        if (total_return > 8 and 
            up_days >= Config.MIN_UP_DAYS and 
            max_dd > -Config.MAX_DRAWDOWN and 
            avg_volume_ratio > Config.VOLUME_INCREASE):
            
            return {
                'Ticker': ticker,
                'Company': yf.Ticker(ticker).info.get('longName', ticker),
                'Current_Price': round(recent['Close'].iloc[-1], 4),
                'Total_Return_%': round(total_return, 2),
                'Up_Days': int(up_days),
                'Max_Drawdown_%': round(max_dd, 2),
                'Volume_Ratio': round(avg_volume_ratio, 2),
                'Last_Date': recent.index[-1].strftime("%Y-%m-%d")
            }
    except:
        pass
    return None

# ==================== 主界面 ====================
with st.sidebar:
    if st.button("🚀 开始扫描美股小票", type="primary"):
        st.session_state.run_scan = True

if st.session_state.get('run_scan', False):
    st.session_state.run_scan = False
    candidates = get_us_small_cap_candidates()
    
    progress_bar = st.progress(0)
    status = st.empty()
    results = []
    
    for i, ticker in enumerate(candidates):
        progress_bar.progress((i + 1) / len(candidates))
        status.text(f"正在分析: {ticker} ({i+1}/{len(candidates)})")
        
        result = analyze_slow_bull(ticker)
        if result:
            results.append(result)
        
        time.sleep(0.8)  # 控制速度
    
    st.session_state.results = results
    st.success(f"扫描完成！发现 {len(results)} 只慢牛小市值股票")
    st.rerun()

# 显示结果
results = st.session_state.get('results', [])
if results:
    df = pd.DataFrame(results)
    df = df.sort_values('Total_Return_%', ascending=False)
    
    st.subheader("📋 慢牛小市值股票列表")
    st.dataframe(df, use_container_width=True, height=600)
    
    # 详情
    ticker_selected = st.selectbox("查看个股详情", df['Ticker'])
    if ticker_selected:
        data = yf.download(ticker_selected, period="3mo")
        col1, col2 = st.columns(2)
        with col1:
            st.line_chart(data['Close'])
        with col2:
            st.bar_chart(data['Volume'])
else:
    st.info("点击左侧按钮开始扫描美股小市值慢牛股票")

st.caption("数据来源于 Yahoo Finance | 适合发现底部缓慢抬升的潜力小票")
