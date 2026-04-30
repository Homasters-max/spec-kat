"""sdd.graph_navigation — BC-36-7 CLI graph navigation handlers.

I-PHASE-ISOLATION-1: this package MUST NOT import sdd.graph.cache or sdd.graph.builder
directly. Use sdd.graph.GraphService as the single entry point (I-GRAPH-SUBSYSTEM-1).

I-RUNTIME-ORCHESTRATOR-1: handlers in this package contain only arg parsing, pipeline
calls, and output formatting — no domain logic.
"""
