# One copy of the system per Tenant

Status: provisional.

A Tenant gets one running copy: one compose project, one database, one set of processes. Not one copy holding several Tenants.

Reason: it matches one database per Tenant, it makes a bank's security review a single diagram, and it makes isolation a fact rather than a filter.

**Trade-off:** a "unified interface" across Tenants is then one UI over several copies, or an aggregation later. That is cheaper than getting the isolation story wrong once.

This reverses if a Tenant turns out to be many organisations under one brand, or if a pilot needs two clients in one copy before they can afford their own. Both would be resolved by Tenancy above Tenant, not by sharing a database.
