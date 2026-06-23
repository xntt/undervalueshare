import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import time

st.set_page_config(page_title="A股小市值监控", layout="wide")

st.title("📊 A股小市值异动监控 - 简化测试版")

if 'alerts' not in st.session_state:
    st.session_state.alerts = []
if 'last_scan' not in st.session_state:
    st.session_state.last_scan = None

# 侧边栏
with st.sidebar:
    st.header("⚙️ 设置")
    max_cap = st.slider("最大市值(亿)", 10, 200, 100)
    days = st.slider("连续上涨天数", 2, 7, 3)
    vol = st.slider("量比阈值", 1.0, 5.0, 2.0)
    
    if st.button("🚀 开始扫描", type="primary", use_container_width=True):
        st.session_state.run_scan = True

# 执行扫描
if st.session_state.get('run_scan', False):
    st.session_state.run_scan = False
    with st.spinner("正在模拟扫描全市场..."):
        time.sleep(2)  # 模拟耗时
        
        # 模拟预警数据
        mock_alerts = [
            {"code": "300750", "name": "宁德时代", "price_change": 8.5, "volume_ratio": 3.2, "current_price": 185.6, "alert_time": datetime.now().strftime("%H:%M")},
            {"code": "000725", "name": "博汇纸业", "price_change": 6.8, "volume_ratio": 4.1, "current_price": 12.4, "alert_time": datetime.now().strftime("%H:%M")},
            {"code": "600519", "name": "贵州茅台", "price_change": 4.2, "volume_ratio": 2.3, "current_price": 1480.0, "alert_time": datetime.now().strftime("%H:%M")},
        ]
        
        st.session_state.alerts = mock_alerts
        st.session_state.last_scan = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.success("✅ 扫描完成！")
        st.rerun()

# 显示结果
alerts = st.session_state.get('alerts', [])
col1, col2, col3 = st.columns(3)
col1.metric("预警数量", len(alerts))
if alerts:
    avg = np.mean([a['price_change'] for a in alerts])
    col2.metric("平均涨幅", f"{avg:.1f}%")
col3.metric("上次扫描", st.session_state.get('last_scan', '从未'))

if alerts:
    df = pd.DataFrame(alerts)
    st.subheader("🚨 预警列表")
    st.dataframe(df, use_container_width=True)
    
    st.subheader("📈 选择查看详情")
    selected = st.selectbox("股票", [f"{a['code']} - {a['name']}" for a in alerts])
    if selected:
        st.success(f"已选择: {selected} （完整K线需本地环境）")
else:
    st.info("👈 请点击左侧「开始扫描」按钮")

st.caption("这是简化测试版，用于验证界面是否正常。\n真实版需要本地电脑或VPS运行。")
