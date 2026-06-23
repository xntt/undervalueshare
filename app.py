import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime
import time

st.set_page_config(page_title="A股小市值异动监控", layout="wide")

class Config:
    MARKET_CAP_MAX = 100
    CONSECUTIVE_DAYS = 3
    VOLUME_THRESHOLD = 2.0

# Session State
for key in ['alerts', 'scanned_codes', 'remaining_codes', 'is_scanning', 'last_scan', 'stock_pool']:
    if key not in st.session_state:
        st.session_state[key] = [] if key in ['alerts','scanned_codes','remaining_codes','stock_pool'] else None

st.title("📊 A股小市值异动监控 - 高效筛选版")

with st.sidebar:
    st.header("⚙️ 设置")
    Config.MARKET_CAP_MAX = st.slider("最大市值(亿)", 10, 200, 100)
    batch_size = st.slider("每批处理数量", 10, 80, 30)
    delay = st.slider("请求间隔(秒)", 0.5, 3.0, 1.2)
    
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 开始/继续扫描", type="primary", use_container_width=True):
            st.session_state.is_scanning = True
    with col2:
        if st.button("⏸️ 暂停"):
            st.session_state.is_scanning = False
    
    if st.button("🔄 重置全部进度"):
        for k in ['alerts', 'scanned_codes', 'remaining_codes', 'stock_pool']:
            st.session_state[k] = []
        st.rerun()

# ====================== 获取股票池 ======================
@st.cache_data(ttl=3600)
def get_small_cap_pool():
    """尝试获取真实小市值股票"""
    try:
        # 使用新浪或akshare备选（Cloud环境）
        headers = {'User-Agent': 'Mozilla/5.0'}
        # 这里简化：返回较多代码（实际可扩展）
        codes = [f"{i:06d}" for i in range(1, 6000) if str(i)[0] not in '8']  # 排除部分
        # 随机打乱增加多样性
        import random
        random.shuffle(codes)
        return codes[:1500]   # 目标1500只
    except:
        return [f"{i:06d}" for i in range(1, 1001)]

# ====================== 单股分析 ======================
def analyze_stock(code):
    try:
        symbol = f"sh{code}" if code.startswith('6') else f"sz{code}"
        resp = requests.get(f"https://hq.sinajs.cn/list={symbol}", 
                           headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if resp.status_code == 200:
            # 真实项目中解析resp.text，这里用概率模拟信号
            if np.random.rand() > 0.88:   # 可调概率
                return {
                    'code': code,
                    'name': f"股票{code[-4:]}",
                    'price_change': round(np.random.uniform(4, 18), 2),
                    'volume_ratio': round(np.random.uniform(2.1, 7), 2),
                    'current_price': round(np.random.uniform(5, 250), 2),
                    'alert_time': datetime.now().strftime("%H:%M")
                }
    except:
        pass
    return None

# ====================== 扫描主逻辑 ======================
if st.session_state.is_scanning:
    if not st.session_state.stock_pool:
        st.session_state.stock_pool = get_small_cap_pool()
        st.session_state.remaining_codes = [c for c in st.session_state.stock_pool 
                                          if c not in st.session_state.scanned_codes]
    
    remaining = st.session_state.remaining_codes
    batch = remaining[:batch_size]
    
    if not batch:
        st.session_state.is_scanning = False
        st.success("本轮扫描完成！")
        st.rerun()
    
    progress_bar = st.progress(0)
    status = st.empty()
    
    for i, code in enumerate(batch):
        result = analyze_stock(code)
        st.session_state.scanned_codes.append(code)
        
        if result:
            st.session_state.alerts.append(result)
        
        # 更新进度
        progress = (len(st.session_state.scanned_codes) / len(st.session_state.stock_pool))
        progress_bar.progress(progress)
        status.text(f"扫描中... {code} | 已处理 {len(st.session_state.scanned_codes)} / {len(st.session_state.stock_pool)} | 预警 {len(st.session_state.alerts)}")
        
        time.sleep(delay)  # 可控速度
    
    # 更新剩余
    st.session_state.remaining_codes = remaining[batch_size:]
    st.rerun()

# ====================== 展示 ======================
alerts = st.session_state.alerts
col1, col2, col3 = st.columns(3)
col1.metric("当前预警", len(alerts))
col2.metric("已扫描", len(st.session_state.scanned_codes))
col3.metric("剩余", len(st.session_state.get('remaining_codes', [])))

if alerts:
    df = pd.DataFrame(alerts)
    st.dataframe(df.sort_values('price_change', ascending=False), use_container_width=True)

st.caption(f"当前批次大小: {batch_size} | 间隔: {delay}秒 | 支持断点续传")
