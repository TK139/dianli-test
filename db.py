# -*- coding: utf-8 -*-
"""Neo4j 数据库连接"""
import os
from neo4j import GraphDatabase


class Neo4jClient:
    def __init__(self):
        uri = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        pwd = os.getenv("NEO4J_PASSWORD", "power123")
        self.driver = GraphDatabase.driver(uri, auth=(user, pwd))

    def run(self, query: str, **params):
        with self.driver.session() as session:
            result = session.run(query, **params)
            return [dict(record) for record in result]

    def close(self):
        self.driver.close()
