# -*- coding: utf-8 -*-
"""
公理推理引擎 — 基于 Neo4j 拓扑执行 SWRL 公理推理
方法: ax001 ~ ax010（已删除 AX-004）
"""
import pandas as pd
from db import Neo4jClient

class ReasoningEngine:
    def __init__(self):
        self.db = Neo4jClient()

    # ---------- 拓扑获取 ----------
    def topology(self):
        """返回 (nodes, edges)"""
        nodes_q = """
        MATCH (n)
        RETURN n.id AS id, labels(n) AS labels, properties(n) AS props
        """
        edges_q = """
        MATCH (a)-[r]->(b)
        RETURN a.id AS start, b.id AS end, type(r) AS type,
               properties(r) AS props
        """
        nodes = [{"id": r["id"], "labels": r["labels"], "props": r["props"]}
                 for r in self.db.run(nodes_q)]
        edges = [{"start": r["start"], "end": r["end"],
                  "type": r["type"], "props": r["props"]}
                 for r in self.db.run(edges_q)]
        return nodes, edges

    # ---------- AX-001 故障传播 ----------
    def ax001_fault_propagation(self, switch_id: str) -> pd.DataFrame:
        q = """
        MATCH path = (s {id: $sid})-[:CONNECTED_TO*1..6]->(downstream)
        WHERE s.id <> downstream.id
        RETURN DISTINCT downstream.id AS device,
               labels(downstream)[0] AS type,
               length(path) AS hops
        ORDER BY hops
        """
        records = list(self.db.run(q, sid=switch_id))
        return pd.DataFrame(records) if records else pd.DataFrame(
            columns=["device", "type", "hops"])

    # ---------- AX-002 过载检测 ----------
    def ax002_overload(self, threshold: float = 0.8) -> pd.DataFrame:
        q = """
        MATCH (t:Transformer)
        WHERE t.rated_kva > 0
        WITH t, t.load_kw / t.rated_kva AS ratio
        WHERE ratio >= $th
        RETURN t.id AS device, t.load_kw AS load_kw,
               t.rated_kva AS rated_kva, round(ratio, 3) AS load_ratio
        ORDER BY load_ratio DESC
        """
        records = list(self.db.run(q, th=threshold))
        return pd.DataFrame(records) if records else pd.DataFrame(
            columns=["device", "load_kw", "rated_kva", "load_ratio"])

    # ---------- AX-003 负荷转供 ----------
    def ax003_transfer(self, source_feeder: str, kw: float) -> pd.DataFrame:
        q = """
        MATCH (f:Feeder {id: $fid})-[:SUPPLIES]->(t:Transformer)
        WITH f, collect(t) AS transformers, sum(t.load_kw) AS total
        MATCH (ts:TieSwitch {status: 'open'})-[:CONNECTED_TO]-(f2:Feeder)
        WHERE f2.id <> f.id
        RETURN f2.id AS target_feeder,
               f2.capacity_kw - f2.load_kw AS margin_kw,
               CASE WHEN f2.capacity_kw - f2.load_kw >= $kw
                    THEN '可转供' ELSE '容量不足' END AS result
        """
        records = list(self.db.run(q, fid=source_feeder, kw=kw))
        return pd.DataFrame(records) if records else pd.DataFrame(
            columns=["target_feeder", "margin_kw", "result"])

    # ---------- AX-005 用户停电 ----------
    def ax005_customer_outage(self, switch_id: str) -> pd.DataFrame:
        q = """
        MATCH (s {id: $sid})-[:CONNECTED_TO*1..6]->(t:Transformer)
              -[:SUPPLIES]->(lp:LoadPoint)
        RETURN DISTINCT lp.id AS load_point,
               lp.customer_count AS customers,
               t.id AS transformer
        """
        records = list(self.db.run(q, sid=switch_id))
        return pd.DataFrame(records) if records else pd.DataFrame(
            columns=["load_point", "customers", "transformer"])

    # ---------- AX-006 检修闭锁 ----------
    def ax006_maintenance_lock(self) -> pd.DataFrame:
        q = """
        MATCH (sw)-[:MAINTENANCE_ON]->(dev)
        RETURN sw.id AS switch, dev.id AS device,
               '禁止操作' AS lock_status
        """
        records = list(self.db.run(q))
        return pd.DataFrame(records) if records else pd.DataFrame(
            columns=["switch", "device", "lock_status"])

    # ---------- AX-007 联络开关合闸校验 ----------
    def ax007_tie_close(self) -> pd.DataFrame:
        q = """
        MATCH (ts:TieSwitch {status: 'open'})-[:CONNECTED_TO]-(f1:Feeder),
              (ts)-[:CONNECTED_TO]-(f2:Feeder)
        WHERE f1.id < f2.id
        RETURN ts.id AS tie_switch, f1.id AS feeder_1, f2.id AS feeder_2,
               CASE WHEN f1.substation = f2.substation
                    THEN '⚠️ 同电源-可合'
                    ELSE '✅ 异电源-可合'
               END AS check_result
        """
        records = list(self.db.run(q))
        return pd.DataFrame(records) if records else pd.DataFrame(
            columns=["tie_switch", "feeder_1", "feeder_2", "check_result"])

    # ---------- AX-008 N-1 校验 ----------
    def ax008_n1(self) -> pd.DataFrame:
        q = """
        MATCH (cb:CircuitBreaker)-[:PROTECTS]->(f:Feeder)
        OPTIONAL MATCH (f)-[:SUPPLIES]->(t:Transformer)
        WITH cb, f, count(t) AS transformer_count
        RETURN cb.id AS breaker, f.id AS feeder,
               transformer_count,
               CASE WHEN transformer_count > 1
                    THEN '⚠️ 失负荷'
                    ELSE '✅ 通过'
               END AS n1_result
        """
        records = list(self.db.run(q))
        return pd.DataFrame(records) if records else pd.DataFrame(
            columns=["breaker", "feeder", "transformer_count", "n1_result"])

    # ---------- AX-009 电压越限 ----------
    def ax009_voltage(self) -> pd.DataFrame:
        q = """
        MATCH (lp:LoadPoint)
        WHERE lp.voltage_pu < 0.95 OR lp.voltage_pu > 1.05
        RETURN lp.id AS device, lp.voltage_pu AS voltage,
               CASE WHEN lp.voltage_pu < 0.95
                    THEN '欠压' ELSE '过压'
               END AS issue
        """
        records = list(self.db.run(q))
        return pd.DataFrame(records) if records else pd.DataFrame(
            columns=["device", "voltage", "issue"])

    # ---------- AX-010 供电恢复 ----------
    def ax010_restore(self, switch_id: str) -> pd.DataFrame:
        q = """
        MATCH (s {id: $sid})-[:CONNECTED_TO*1..6]->(t:Transformer)
        OPTIONAL MATCH (t)-[:SUPPLIES]->(lp:LoadPoint)
        OPTIONAL MATCH (ts:TieSwitch {status:'open'})-[:CONNECTED_TO]
              (alt:Feeder)-[:SUPPLIES]->(t)
        RETURN t.id AS transformer,
               lp.id AS load_point,
               alt.id AS alt_feeder,
               CASE WHEN alt IS NOT NULL
                    THEN '可转供' ELSE '需发电车'
               END AS restore_plan
        """
        records = list(self.db.run(q, sid=switch_id))
        return pd.DataFrame(records) if records else pd.DataFrame(
            columns=["transformer", "load_point", "alt_feeder", "restore_plan"])