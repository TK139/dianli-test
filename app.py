# -*- coding: utf-8 -*-
"""
配电网本体知识图谱 · 主应用
5 Tabs: 交互拓扑 / 本体模型 / 公理推理 / 告警分析 / AI推理
"""
import streamlit as st
import yaml
import pandas as pd
from pyvis.network import Network
from db import Neo4jClient
from reasoning import ReasoningEngine
from llm_agent import OntologyLLMAgent

# ==================== 页面配置 ====================
st.set_page_config(page_title="配电网本体知识图谱", page_icon="⚡", layout="wide")

# ==================== 缓存加载 ====================
@st.cache_data
def load_ontology():
    with open("power_ontology.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)

@st.cache_resource
def get_engine():
    return ReasoningEngine()

@st.cache_resource
def get_db():
    return Neo4jClient()

@st.cache_resource
def get_agent():
    try:
        return OntologyLLMAgent()
    except Exception as e:
        return None

# ==================== 工具函数 ====================
def _ensure_list(val):
    """确保值为列表"""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]

def build_ontology_graph(onto):
    """构建本体 Schema 可视化"""
    net = Network(height="520px", width="100%", directed=True, notebook=False)
    net.barnes_hut(gravity=-3000, central_gravity=0.3, spring_length=150)

    # 节点
    for c in onto.get("classes", []):
        net.add_node(c["id"], label=f"{c['id']}\n{c.get('label','')}",
                      title=f"类: {c.get('label','')}",
                      color="#4A90D9", shape="box", font={"size": 13})

    # 属性边
    for p in onto.get("object_properties", []):
        domains = _ensure_list(p.get("domain"))
        ranges  = _ensure_list(p.get("range"))
        for d in domains:
            for r in ranges:
                if d and r:
                    net.add_edge(d, r, title=p.get("label", p["id"]),
                                 label=p.get("label", p["id"]),
                                 arrows="to", color="#E67E22")

    # 继承边
    for c in onto.get("classes", []):
        parents = _ensure_list(c.get("subClassOf"))
        for p in parents:
            if p:
                net.add_edge(c["id"], p, title="subClassOf",
                             label="⊆", arrows="to",
                             color="#95A5A6", dashes=True)
    return net

def build_topology_graph(engine):
    """构建实时拓扑可视化"""
    net = Network(height="520px", width="100%", directed=False, notebook=False)
    net.barnes_hut(gravity=-2500, central_gravity=0.2, spring_length=120)

    nodes, edges = engine.topology()
    color_map = {
        "Substation": "#E74C3C", "Feeder": "#F39C12",
        "CircuitBreaker": "#2ECC71", "SectionalizingSwitch": "#3498DB",
        "TieSwitch": "#9B59B6", "Transformer": "#1ABC9C",
        "LoadPoint": "#E67E22", "Bus": "#7F8C8D",
    }

    for n in nodes:
        lbl = n["labels"][0] if n["labels"] else "Unknown"
        nid = n["id"]
        props_str = "<br>".join(f"{k}: {v}" for k, v in n["props"].items())
        net.add_node(nid, label=nid, title=f"<b>{lbl}</b><br>{props_str}",
                      color=color_map.get(lbl, "#BDC3C7"),
                      shape="dot" if lbl != "Substation" else "box",
                      font={"size": 12})

    for e in edges:
        net.add_edge(e["start"], e["end"],
                      title=e.get("type", ""),
                      label=e.get("type", ""),
                      color="#AAB7B8")
    return net

# ==================== 侧边栏 ====================
with st.sidebar:
    st.title("⚡ 配电网本体知识图谱")
    onto = load_ontology()
    engine = get_engine()
    db = get_db()

    st.markdown("---")
    st.markdown(f"**本体:** {onto.get('name', 'PowerOntology')}")
    st.markdown(f"**类:** {len(onto.get('classes', []))} | "
                f"**属性:** {len(onto.get('object_properties', []))} | "
                f"**公理:** {len(onto.get('axioms', []))}")
    st.markdown("---")

    # 拓扑统计
    try:
        nodes, edges = engine.topology()
        st.markdown(f"**实时拓扑:** {len(nodes)} 节点 / {len(edges)} 边")
    except:
        st.warning("Neo4j 未连接")

# ==================== 5 Tabs ====================
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["🗺️交互拓扑", "🧬本体模型", "🧠公理推理", "⚠️告警分析", "🤖AI推理"]
)

# ==================== Tab1 交互拓扑 ====================
with tab1:
    st.subheader("🗺️ 配电网实时拓扑")
    try:
        topo_net = build_topology_graph(engine)
        topo_net.save_graph("topology.html")
        with open("topology.html", encoding="utf-8") as f:
            st.components.v1.html(f.read(), height=560, scrolling=True)
    except Exception as e:
        st.error(f"拓扑加载失败: {e}")

# ==================== Tab2 本体模型 ====================
with tab2:
    st.subheader("🧬 本体 Schema 结构")

    col_a, col_b = st.columns([3, 1])
    with col_a:
        try:
            onto_net = build_ontology_graph(onto)
            onto_net.save_graph("ontology.html")
            with open("ontology.html", encoding="utf-8") as f:
                st.components.v1.html(f.read(), height=560, scrolling=True)
        except Exception as e:
            st.error(f"本体图加载失败: {e}")

    with col_b:
        st.markdown("**📋 类列表**")
        cls_df = pd.DataFrame([
            {"ID": c["id"], "名称": c.get("label", ""), "父类": str(c.get("subClassOf", ""))}
            for c in onto.get("classes", [])
        ])
        st.dataframe(cls_df, use_container_width=True, height=260)

        st.markdown("**🔗 属性列表**")
        prop_df = pd.DataFrame([
            {"ID": p["id"], "名称": p.get("label", ""),
             "Domain": str(p.get("domain", "")), "Range": str(p.get("range", ""))}
            for p in onto.get("object_properties", [])
        ])
        st.dataframe(prop_df, use_container_width=True, height=260)

# ==================== Tab3 公理推理 ====================
with tab3:
    st.subheader("🧠 公理推理引擎")

    axioms = onto.get("axioms", [])
    ax_options = {a["id"]: f"{a['id']} {a['name']}" for a in axioms}
    ax_id = st.selectbox("选择公理:", list(ax_options.keys()),
                          format_func=lambda x: ax_options[x])

    selected_ax = next((a for a in axioms if a["id"] == ax_id), None)
    if selected_ax:
        st.info(f"**描述:** {selected_ax.get('description', '')}")
        st.code(selected_ax.get("swrl", ""), language="text")

    st.markdown("---")

    if ax_id == "AX-001":
        sw = st.text_input("开关ID:", "S-001")
        if st.button("▶ 执行推理", type="primary"):
            st.dataframe(engine.ax001_fault_propagation(sw), use_container_width=True)

    elif ax_id == "AX-002":
        th = st.slider("过载阈值:", 0.0, 1.0, 0.8, 0.05)
        if st.button("▶ 执行推理", type="primary"):
            st.dataframe(engine.ax002_overload(th), use_container_width=True)

    elif ax_id == "AX-003":
        src = st.text_input("源馈线:", "F-001")
        kw  = st.number_input("转移负荷(kW):", min_value=0, value=200)
        if st.button("▶ 执行推理", type="primary"):
            st.dataframe(engine.ax003_transfer(src, kw), use_container_width=True)

    elif ax_id == "AX-005":
        dev = st.text_input("开关/设备ID:", "S-001")
        if st.button("▶ 执行推理", type="primary"):
            st.dataframe(engine.ax005_customer_outage(dev), use_container_width=True)

    elif ax_id == "AX-006":
        if st.button("▶ 执行推理", type="primary"):
            st.dataframe(engine.ax006_maintenance_lock(), use_container_width=True)

    elif ax_id == "AX-007":
        if st.button("▶ 执行推理", type="primary"):
            st.dataframe(engine.ax007_tie_close(), use_container_width=True)

    elif ax_id == "AX-008":
        if st.button("▶ 执行推理", type="primary"):
            st.dataframe(engine.ax008_n1(), use_container_width=True)

    elif ax_id == "AX-009":
        if st.button("▶ 执行推理", type="primary"):
            st.dataframe(engine.ax009_voltage(), use_container_width=True)

    elif ax_id == "AX-010":
        dev = st.text_input("故障设备:", "S-001")
        if st.button("▶ 执行推理", type="primary"):
            st.dataframe(engine.ax010_restore(dev), use_container_width=True)

# ==================== Tab4 告警分析 ====================
with tab4:
    st.subheader("⚠️ 实时告警分析")

    if st.button("🔍 扫描当前电网状态", type="primary"):
        alerts = []
        try:
            # 过载
            ol = engine.ax002_overload(0.8)
            for _, row in ol.iterrows():
                alerts.append({"级别": "🔴 严重", "类型": "过载",
                               "设备": row.get("device", ""),
                               "详情": f"负载率 {row.get('load_ratio', '')}"} )
        except: pass

        try:
            # 电压越限
            vl = engine.ax009_voltage()
            for _, row in vl.iterrows():
                alerts.append({"级别": "🟡 警告", "类型": "电压越限",
                               "设备": row.get("device", ""),
                               "详情": f"电压 {row.get('voltage', '')}"} )
        except: pass

        try:
            # N-1
            n1 = engine.ax008_n1()
            for _, row in n1.iterrows():
                if str(row.get("pass", "")).lower() in ("false", "no", "0"):
                    alerts.append({"级别": "🟡 警告", "类型": "N-1不通过",
                                   "设备": row.get("device", ""),
                                   "详情": str(row.get("detail", ""))})
        except: pass

        if alerts:
            st.dataframe(pd.DataFrame(alerts), use_container_width=True)
            st.warning(f"共发现 **{len(alerts)}** 条告警")
        else:
            st.success("✅ 当前电网运行正常，未发现告警")

# ==================== Tab5 AI推理（含验证题目） ====================
# ==================== Tab5 AI推理（含验证题目） ====================
with tab5:
    st.subheader("🤖 大模型 × 本体 融合推理")
    st.caption("基于本体知识 + 实时拓扑 + 推理引擎，支持示例验证与自然语言自由提问")

    # ---------- 初始化 ----------
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "pending_question" not in st.session_state:
        st.session_state.pending_question = None

    agent = get_agent()

    if agent is None:
        st.error("❌ LLM 未初始化，请检查 `llm_config.yaml` 中的 API Key 配置")
        st.stop()

    # ---------- 示例验证题（写死5题，按钮直接触发） ----------
    st.markdown("### 📋 示例验证题目")

    EXAMPLES = [
        ("Q1 · 故障传播分析 (AX-001)",
         "S-001 开关发生故障断开后，故障如何沿拓扑传播？请分析影响范围并给出隔离建议。"),
        ("Q2 · 过载检测 (AX-002)",
         "当前电网中哪些配电变压器存在过载风险？请给出负荷调整建议。"),
        ("Q3 · 负荷转供 (AX-003)",
         "馈线 F-001 计划检修，请分析负荷转供方案，确保用户不停电。"),
        ("Q4 · 用户停电影响 (AX-005)",
         "S-001 断开后，哪些用户会停电？影响范围多大？如何快速恢复供电？"),
        ("Q5 · N-1 安全校验 (AX-008)",
         "当前电网 N-1 校验是否全部通过？薄弱环节在哪里？如何加固？"),
    ]

    for label, question in EXAMPLES:
        with st.expander(label, expanded=False):
            st.markdown(f"> {question}")
            if st.button("🚀 开始推理", key=f"run_{label}"):
                st.session_state.pending_question = question
                st.rerun()

    st.markdown("---")
    st.markdown("### 💬 对话记录")

    # ---------- 渲染历史对话 ----------
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("tool_used"):
                st.caption(f"🔧 调用工具: `{msg['tool_used']}`")

    # ---------- 处理待执行的问题 ----------
    def do_reason(question: str):
        """执行推理并更新对话"""
        st.session_state.chat_history.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("🧠 正在推理中..."):
                try:
                    result = agent.smart_reason(
                        question,
                        history=st.session_state.chat_history[:-1]
                    )
                    answer = result["answer"]
                    tool   = result.get("tool_used")

                    if tool:
                        st.info(f"🔧 已调用推理工具: `{tool}`")
                    st.markdown(answer)

                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": answer,
                        "tool_used": tool,
                    })
                except Exception as e:
                    err = f"❌ 推理出错: {e}"
                    st.error(err)
                    st.session_state.chat_history.append({
                        "role": "assistant", "content": err
                    })

    if st.session_state.pending_question:
        q = st.session_state.pending_question
        st.session_state.pending_question = None
        do_reason(q)
        st.rerun()

    # ---------- 自由提问输入框 ----------
    user_input = st.chat_input("输入你的问题，如：T-005 过载了怎么办？")
    if user_input:
        do_reason(user_input)