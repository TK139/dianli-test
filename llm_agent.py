# -*- coding: utf-8 -*-
"""
LLM + 本体融合推理引擎
支持：自然语言问答 / 故障推理 / 运行方式分析 / 工具自动路由
"""
import yaml
import json
import re
from openai import OpenAI
from db import Neo4jClient
from reasoning import ReasoningEngine


class OntologyLLMAgent:
    """大模型 × 本体 融合推理 Agent"""

    def __init__(self, config_path="llm_config.yaml", ontology_path="power_ontology.yaml"):
        # 读取 LLM 配置
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)["llm"]

        self.client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
        self.model       = cfg["model"]
        self.temperature = cfg.get("temperature", 0.3)
        self.max_tokens  = cfg.get("max_tokens", 2048)

        # 读取本体知识
        with open(ontology_path, encoding="utf-8") as f:
            self.ontology = yaml.safe_load(f)

        self.engine = ReasoningEngine()

    # ==================== 提示词构建 ====================
    def _build_system_prompt(self) -> str:
        """将本体结构注入系统提示词"""
        classes = "\n".join(
            f"- {c['id']}({c.get('label','')}): 父类={c.get('subClassOf','无')}"
            for c in self.ontology.get("classes", [])
        )
        obj_props = "\n".join(
            f"- {p['id']}: {p.get('domain','')} → {p.get('range','')} ({p.get('label','')})"
            for p in self.ontology.get("object_properties", [])
        )
        axioms = "\n".join(
            f"- {a['id']} {a['name']}: {a['description']}"
            for a in self.ontology.get("axioms", [])
        )

        return f"""你是一位配电网领域专家，精通电力系统拓扑分析、故障推理和运行方式优化。
请严格基于以下本体知识图谱进行推理分析。

## 本体类定义
{classes}

## 对象属性（关系）
{obj_props}

## 推理公理
{axioms}

## 回答要求
1. 基于本体定义进行严格逻辑推理，引用具体公理编号
2. 涉及具体设备时，说明推理路径（如 A→B→C）
3. 给出明确结论和可操作的建议
4. 使用中文回答，专业术语保持准确
5. 如果数据不足以得出结论，明确说明"""

    # ==================== 实时拓扑上下文 ====================
    def _get_topology_context(self) -> str:
        """从推理引擎获取当前电网摘要"""
        try:
            nodes, edges = self.engine.topology()
            summary = f"当前电网包含 {len(nodes)} 个设备节点，{len(edges)} 条连接关系。\n"

            type_count = {}
            for n in nodes:
                lt = n["labels"][0] if n["labels"] else "Unknown"
                type_count[lt] = type_count.get(lt, 0) + 1
            summary += "设备分布: " + ", ".join(f"{k}×{v}" for k, v in type_count.items()) + "\n"

            switches = [n for n in nodes if n["labels"] and
                        n["labels"][0] in ("CircuitBreaker", "SectionalizingSwitch", "TieSwitch")]
            closed = [s["id"] for s in switches if s["props"].get("status") == "closed"]
            opened = [s["id"] for s in switches if s["props"].get("status") == "open"]
            if closed:
                summary += f"合闸开关: {', '.join(closed)}\n"
            if opened:
                summary += f"分闸开关: {', '.join(opened)}\n"
            return summary
        except Exception as e:
            return f"（拓扑数据暂不可用: {e}）"

    # ==================== 工具调用 ====================
    TOOL_REGISTRY = {
        "ax001_fault_propagation": {"desc": "故障传播分析", "params": ["switch_id"]},
        "ax002_overload":          {"desc": "过载检测",     "params": ["threshold"]},
        "ax003_transfer":          {"desc": "负荷转供分析", "params": ["source_feeder", "kw"]},
        "ax005_customer_outage":   {"desc": "用户停电分析", "params": ["switch_id"]},
        "ax006_maintenance_lock":  {"desc": "检修闭锁查询", "params": []},
        "ax007_tie_close":         {"desc": "联络开关合闸校验", "params": []},
        "ax008_n1":                {"desc": "N-1校验",      "params": []},
        "ax009_voltage":           {"desc": "电压越限检查", "params": []},
        "ax010_restore":           {"desc": "供电恢复分析", "params": ["switch_id"]},
    }

    def _call_tool(self, tool_name: str, **kwargs):
        """调用推理引擎方法"""
        try:
            method = getattr(self.engine, tool_name)
            result = method(**kwargs)
            return json.dumps(result, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            return f"工具调用失败: {e}"

    # ==================== 工具路由 ====================
    def _route_tool(self, user_query: str) -> dict:
        """让 LLM 判断是否需要调用推理工具"""
        tool_desc = "\n".join(
            f"{i+1}. {name}({', '.join(info['params'])}) - {info['desc']}"
            for i, (name, info) in enumerate(self.TOOL_REGISTRY.items())
        )

        prompt = f"""用户问题: "{user_query}"

可用推理工具:
{tool_desc}

判断是否需要调用工具。以 JSON 回答:
{{"need_tool": true/false, "tool": "工具名", "params": {{...}}}}
只输出 JSON。"""

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是工具路由器，只输出JSON，不要解释。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=200,
            )
            text = resp.choices[0].message.content.strip()
            m = re.search(r"\{.*\}", text, re.DOTALL)
            return json.loads(m.group()) if m else {"need_tool": False}
        except Exception:
            return {"need_tool": False}

    # ==================== 核心推理 ====================
    def reason(self, user_query: str, history: list = None) -> str:
        """纯 LLM 推理"""
        messages = [
            {"role": "system", "content": self._build_system_prompt()},
            {"role": "system", "content": f"## 当前电网实时状态\n{self._get_topology_context()}"},
        ]
        if history:
            messages.extend(history[-10:])
        messages.append({"role": "user", "content": user_query})

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return resp.choices[0].message.content

    def smart_reason(self, user_query: str, history: list = None) -> dict:
        """
        增强推理：工具路由 → 数据获取 → 综合回答
        返回 {"answer": str, "tool_used": str|None, "tool_result": str|None}
        """
        # 1) 路由判断
        route = self._route_tool(user_query)
        tool_result = None
        tool_used   = None

        # 2) 调用工具
        if route.get("need_tool") and route.get("tool") in self.TOOL_REGISTRY:
            tool_name = route["tool"]
            params    = route.get("params", {})
            tool_result = self._call_tool(tool_name, **params)
            tool_used   = tool_name

        # 3) 综合推理
        query = user_query
        if tool_result:
            query += (f"\n\n[推理引擎 {tool_used} 返回数据]:\n{tool_result}\n\n"
                      f"请基于以上数据和本体知识，给出完整分析结论与操作建议。")

        answer = self.reason(query, history)

        return {"answer": answer, "tool_used": tool_used, "tool_result": tool_result}