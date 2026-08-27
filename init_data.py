# -*- coding: utf-8 -*-
"""
配电网本体知识图谱 · 数据初始化脚本
功能:
  1. 读取 power_ontology.yaml，创建本体 Schema（类、属性、公理）
  2. 插入示例配电网拓扑数据（变电站、馈线、开关、配变、负荷点）
  3. 建立设备间连接关系

用法:
  python init_data.py              # 本地运行
  docker exec -it app python init_data.py   # 容器内运行
"""
import os
import yaml
from db import Neo4jClient


def load_ontology(path="power_ontology.yaml"):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def clear_database(db: Neo4jClient):
    """清空数据库（谨慎使用）"""
    print("🗑️  清空现有数据...")
    db.run("MATCH (n) DETACH DELETE n")
    print("✅ 数据库已清空")


def create_schema(db: Neo4jClient, onto: dict):
    """根据本体 YAML 创建类节点和属性定义"""
    print("\n📐 创建本体 Schema...")

    # 1) 创建类节点
    for cls in onto.get("classes", []):
        props = {
            "id": cls["id"],
            "label": cls.get("label", cls["id"]),
            "description": cls.get("description", ""),
        }
        parents = cls.get("subClassOf")
        if isinstance(parents, str):
            parents = [parents]
        elif parents is None:
            parents = []

        db.run("""
            MERGE (c:OntologyClass {id: $id})
            SET c.label = $label, c.description = $description
        """, **props)

        for parent in parents:
            db.run("""
                MATCH (child:OntologyClass {id: $child_id})
                MERGE (parent:OntologyClass {id: $parent_id})
                MERGE (child)-[:SUBCLASS_OF]->(parent)
            """, child_id=cls["id"], parent_id=parent)

    print(f"   ✅ 创建了 {len(onto.get('classes', []))} 个类")

    # 2) 创建对象属性
    for prop in onto.get("object_properties", []):
        domains = prop.get("domain", [])
        ranges  = prop.get("range", [])
        if isinstance(domains, str):
            domains = [domains]
        if isinstance(ranges, str):
            ranges = [ranges]

        db.run("""
            MERGE (p:ObjectProperty {id: $id})
            SET p.label = $label, p.description = $description
        """, id=prop["id"],
            label=prop.get("label", prop["id"]),
            description=prop.get("description", ""))

        for d in domains:
            for r in ranges:
                db.run("""
                    MATCH (dp:OntologyClass {id: $did})
                    MATCH (rp:OntologyClass {id: $rid})
                    MATCH (op:ObjectProperty {id: $pid})
                    MERGE (op)-[:HAS_DOMAIN]->(dp)
                    MERGE (op)-[:HAS_RANGE]->(rp)
                """, did=d, rid=r, pid=prop["id"])

    print(f"   ✅ 创建了 {len(onto.get('object_properties', []))} 个对象属性")

    # 3) 创建公理节点
    for ax in onto.get("axioms", []):
        db.run("""
            MERGE (a:Axiom {id: $id})
            SET a.name = $name,
                a.swrl = $swrl,
                a.description = $description
        """, id=ax["id"],
            name=ax.get("name", ""),
            swrl=ax.get("swrl", ""),
            description=ax.get("description", ""))

    print(f"   ✅ 创建了 {len(onto.get('axioms', []))} 条公理")


def insert_sample_topology(db: Neo4jClient):
    """插入示例配电网拓扑数据"""
    print("\n⚡ 插入示例电网拓扑数据...")

    # ===== 变电站 =====
    substations = [
        {"id": "SS-01", "name": "城东变电站", "voltage_level": "110kV"},
        {"id": "SS-02", "name": "城西变电站", "voltage_level": "110kV"},
    ]
    for ss in substations:
        db.run("""
            MERGE (n:Substation {id: $id})
            SET n.name = $name, n.voltage_level = $voltage_level
        """, **ss)
    print(f"   ✅ 变电站 ×{len(substations)}")

    # ===== 母线 =====
    buses = [
        {"id": "BUS-01", "substation": "SS-01", "voltage_kv": 10.5},
        {"id": "BUS-02", "substation": "SS-01", "voltage_kv": 10.5},
        {"id": "BUS-03", "substation": "SS-02", "voltage_kv": 10.5},
    ]
    for bus in buses:
        db.run("""
            MERGE (n:Bus {id: $id})
            SET n.substation = $substation, n.voltage_kv = $voltage_kv
        """, **bus)
        db.run("""
            MATCH (b:Bus {id: $bid}), (s:Substation {id: $sid})
            MERGE (b)-[:BELONGS_TO]->(s)
        """, bid=bus["id"], sid=bus["substation"])
    print(f"   ✅ 母线 ×{len(buses)}")

    # ===== 馈线 =====
    feeders = [
        {"id": "F-001", "name": "城东I线", "substation": "SS-01",
         "capacity_kw": 3000, "load_kw": 2200},
        {"id": "F-002", "name": "城东II线", "substation": "SS-01",
         "capacity_kw": 3000, "load_kw": 1800},
        {"id": "F-003", "name": "城西I线", "substation": "SS-02",
         "capacity_kw": 3000, "load_kw": 2500},
    ]
    for f in feeders:
        db.run("""
            MERGE (n:Feeder {id: $id})
            SET n.name = $name, n.substation = $substation,
                n.capacity_kw = $capacity_kw, n.load_kw = $load_kw
        """, **f)
    print(f"   ✅ 馈线 ×{len(feeders)}")

    # ===== 断路器 =====
    breakers = [
        {"id": "CB-01", "feeder": "F-001", "status": "closed"},
        {"id": "CB-02", "feeder": "F-002", "status": "closed"},
        {"id": "CB-03", "feeder": "F-003", "status": "closed"},
    ]
    for cb in breakers:
        db.run("""
            MERGE (n:CircuitBreaker {id: $id})
            SET n.status = $status
        """, **cb)
        db.run("""
            MATCH (cb:CircuitBreaker {id: $cbid}), (f:Feeder {id: $fid})
            MERGE (cb)-[:PROTECTS]->(f)
        """, cbid=cb["id"], fid=cb["feeder"])
    print(f"   ✅ 断路器 ×{len(breakers)}")

    # ===== 分段开关 =====
    sectionals = [
        {"id": "S-001", "status": "closed"},
        {"id": "S-002", "status": "closed"},
        {"id": "S-003", "status": "closed"},
        {"id": "S-004", "status": "open"},
    ]
    for sw in sectionals:
        db.run("""
            MERGE (n:SectionalizingSwitch {id: $id})
            SET n.status = $status
        """, **sw)
    print(f"   ✅ 分段开关 ×{len(sectionals)}")

    # ===== 联络开关 =====
    ties = [
        {"id": "TS-01", "status": "open",
         "feeder_a": "F-001", "feeder_b": "F-003"},
        {"id": "TS-02", "status": "open",
         "feeder_a": "F-002", "feeder_b": "F-003"},
    ]
    for ts in ties:
        db.run("""
            MERGE (n:TieSwitch {id: $id})
            SET n.status = $status
        """, **ts)
        db.run("""
            MATCH (ts:TieSwitch {id: $tsid}), (fa:Feeder {id: $fa})
            MERGE (ts)-[:CONNECTED_TO]->(fa)
        """, tsid=ts["id"], fa=ts["feeder_a"])
        db.run("""
            MATCH (ts:TieSwitch {id: $tsid}), (fb:Feeder {id: $fb})
            MERGE (ts)-[:CONNECTED_TO]->(fb)
        """, tsid=ts["id"], fb=ts["feeder_b"])
    print(f"   ✅ 联络开关 ×{len(ties)}")

    # ===== 配电变压器 =====
    transformers = [
        {"id": "T-001", "rated_kva": 630,  "load_kw": 480,
         "feeder": "F-001", "voltage_pu": 1.02},
        {"id": "T-002", "rated_kva": 400,  "load_kw": 350,
         "feeder": "F-001", "voltage_pu": 0.98},
        {"id": "T-003", "rated_kva": 800,  "load_kw": 720,
         "feeder": "F-002", "voltage_pu": 1.01},
        {"id": "T-004", "rated_kva": 500,  "load_kw": 460,
         "feeder": "F-002", "voltage_pu": 0.94},
        {"id": "T-005", "rated_kva": 630,  "load_kw": 580,
         "feeder": "F-003", "voltage_pu": 1.06},
        {"id": "T-006", "rated_kva": 400,  "load_kw": 310,
         "feeder": "F-003", "voltage_pu": 0.97},
    ]
    for t in transformers:
        db.run("""
            MERGE (n:Transformer {id: $id})
            SET n.rated_kva = $rated_kva, n.load_kw = $load_kw,
                n.voltage_pu = $voltage_pu
        """, **t)
        db.run("""
            MATCH (t:Transformer {id: $tid}), (f:Feeder {id: $fid})
            MERGE (f)-[:SUPPLIES]->(t)
        """, tid=t["id"], fid=t["feeder"])
    print(f"   ✅ 配电变压器 ×{len(transformers)}")

    # ===== 负荷点 =====
    loads = [
        {"id": "LP-001", "transformer": "T-001", "customer_count": 120},
        {"id": "LP-002", "transformer": "T-002", "customer_count": 85},
        {"id": "LP-003", "transformer": "T-003", "customer_count": 200},
        {"id": "LP-004", "transformer": "T-004", "customer_count": 95},
        {"id": "LP-005", "transformer": "T-005", "customer_count": 150},
        {"id": "LP-006", "transformer": "T-006", "customer_count": 70},
    ]
    for lp in loads:
        db.run("""
            MERGE (n:LoadPoint {id: $id})
            SET n.customer_count = $customer_count
        """, **lp)
        db.run("""
            MATCH (t:Transformer {id: $tid}), (lp:LoadPoint {id: $lpid})
            MERGE (t)-[:SUPPLIES]->(lp)
        """, tid=lp["transformer"], lpid=lp["id"])
    print(f"   ✅ 负荷点 ×{len(loads)}")

    # ===== 拓扑连接关系（分段开关 ↔ 馈线/配变） =====
    connections = [
        ("S-001", "F-001"), ("S-001", "T-001"),
        ("S-002", "T-001"), ("S-002", "T-002"),
        ("S-003", "F-002"), ("S-003", "T-003"),
        ("S-004", "T-003"), ("S-004", "T-004"),
    ]
    for src, dst in connections:
        db.run("""
            MATCH (a {id: $src}), (b {id: $dst})
            MERGE (a)-[:CONNECTED_TO]->(b)
        """, src=src, dst=dst)
    print(f"   ✅ 连接关系 ×{len(connections)}")


def main():
    print("=" * 50)
    print("⚡ 配电网本体知识图谱 · 数据初始化")
    print("=" * 50)

    db = Neo4jClient()
    onto = load_ontology()

    # 可选：是否清空重建
    force = os.getenv("INIT_FORCE", "false").lower() == "true"
    if force:
        clear_database(db)

    create_schema(db, onto)
    insert_sample_topology(db)

    print("\n" + "=" * 50)
    print("✅ 数据初始化完成！")
    print("=" * 50)

    db.close()


if __name__ == "__main__":
    main()