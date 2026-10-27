# Workflows are data, owned by one Tenant

A Workflow is an ordered list of Steps in the Tenant's Pack. Each Step names one verb from a fixed set of seven and gives it inputs. There is no loop, no conditional and no sub-Workflow.

A Workflow belongs to exactly one Tenant. There is no shared library, no base Workflow, no inheritance and no registry. Two banks may both run a "taxes" Workflow; they are two files that started from the same copy. **Copy, never share.**

Rejected: code per client (that is a fork by another name); a shared definition that several Tenants reference (one change must then satisfy two compliance teams and two change-control processes); a general DSL with branching.

**Consequence:** a fix to one Tenant's Workflow does not reach the others. That is the price of independence and it is paid on purpose.
