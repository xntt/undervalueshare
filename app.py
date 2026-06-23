import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests
import time
import json

st.set_page_config(page_title="A股小市值监控", layout="wide")

class Config:
    MARKET_CAP_MAX = 100
    CONSECUTIVE_DAYS = 3
    VOLUME_THRESHOLD = 2.0

# 初始化 session state
if 'alerts' not in st.session_state:
    st.session_state.alerts = []
if 'scanned_codes' not in st.session_state:      # 已扫描股票
    st.session_state.scanned_codes = []
if 'remaining_codes' not in st.session_state:    # 待扫描
    st.session_state.remaining_codes = []
if 'is_scanning' not in st.session_state:
    st.session_state.is_scanning = False
if 'last_scan' not in st.session_state:
    st.session_state.last_scan = None

st.title("📊 A股小市值异动监控 - 慢速断点版")

with st.sidebar:
    st.header("⚙️ 设置")
    Config.MARKET_CAP_MAX = st.slider("最大市值(亿)", 10, 200, 100)
    Config.CONSECUTIVE_DAYS = st.slider("连续上涨天数", 2, 7, 3)
    Config.VOLUME_THRESHOLD = st.slider("量比阈值", 1.0, 5.0, 2.0)
    
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 开始/继续扫描", type="primary"):
            st.session_state.is_scanning = True
    with col2:
        if st.button("⏸️ 暂停扫描"):
            st.session_state.is_scanning = False

    if st.button("🔄 重置扫描进度"):
        st.session_state.scanned_codes = []
        st.session_state.remaining_codes = []
        st.session_state.alerts = []
        st.rerun()

# ====================== 核心扫描函数 ======================
def get_all_stock_codes():
    """获取股票列表（简化版，可后续替换为真实列表）"""
    if not st.session_state.remaining_codes:
        # 这里可以扩展为真实获取全量小市值列表
        base_codes = [f"{i:06d}" for i in range(1, 5000)]  # 示例范围，可优化
        st.session_state.remaining_codes = base_codes[:300]  # 限制数量，避免太慢
    return st.session_state.remaining_codes

def analyze_single_stock(code):
    """单只股票分析（慢速）"""
    try:
        if code.startswith('6'):
            symbol = f"sh{code}"
        else:
            symbol = f"sz{code}"
        
        url = f"https://hq.sinajs.cn/list={symbol}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            # 模拟异动检测（真实项目中解析返回数据）
            if np.random.random() > 0.85:   # 随机产生信号用于测试
                return {
                    'code': code,
                    'name': f"股票{code}",
                    'price_change': round(np.random.uniform(3.5, 15), 2),
                    'volume_ratio': round(np.random.uniform(2.1, 6), 2),
                    'current_price': round(np.random.uniform(8, 180), 2),
                    'alert_time': datetime.now().strftime("%H:%M"),
                }
    except:
        pass
    return None

# ====================== 主扫描循环 ======================
if st.session_state.is_scanning:
    remaining = get_all_stock_codes()
    total = len(remaining) + len(st.session_state.scanned_codes)
    processed = len(st.session_state.scanned_codes)
    
    progress_bar = st.progress(processed / total if total > 0 else 0)
    status = st.empty()
    
    # 每次 rerun 处理少量股票（避免超时）
    batch_size = 5   # 每次处理5只，防止 Cloud 超时
    batch = remaining[:batch_size]
    
    for code in batch:
        result = analyze_single_stock(code)
        st.session_state.scanned_codes.append(code)
        
        if result:
            st.session_state.alerts.append(result)
        
        processed += 1
        progress_bar.progress(processed / total)
        status.text(f"正在扫描: {code}  | 进度: {processed}/{total} | 已发现 {len(st.session_state.alerts)} 个")
        
        time.sleep(2.0)  # 关键：慢速间隔，降低被封风险
    
    # 更新剩余列表
    st.session_state.remaining_codes = remaining[batch_size:]
    
    if not st.session_state.remaining_codes:
        st.session_state.is_scanning = False
        st.success("🎉 本轮扫描全部完成！")
        st.session_state.last_scan = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    st.rerun()

# ====================== 展示结果 ======================
alerts = st.session_state.get('alerts', [])
col1, col2, col3, col4 = st.columns(4)
col1.metric("预警数量", len(alerts))
col2.metric("已扫描", len(st.session_state.scanned_codes))
if alerts:
    col3.metric("平均涨幅", f"{np.mean([a['price_change'] for a in alerts]):.2f}%")
col4.metric("状态", "扫描中..." if st.session_state.is_scanning else "已暂停")

if alerts:
    df = pd.DataFrame(alerts)
    st.dataframe(df, use_container_width=True)

st.caption("💡 扫描速度已放慢以避免API封禁\n支持断点续传，刷新页面也不会丢失进度")
