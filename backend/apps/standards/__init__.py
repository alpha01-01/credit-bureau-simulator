"""Industry standards shared by every party in the simulated market.

The credit data submission template and its code lists are published rules:
lenders write files to them and the bureau validates against them. They are
therefore neither world truth nor bureau internals, and this package imports
nothing else from ``apps`` (enforced by import-linter).
"""
