"""Thin adapters over the commission_ingestion store classes.

These translate between the stores' return types and the API schemas. They hold
no Cypher and no ingestion logic; all queries live in the package stores.
"""
