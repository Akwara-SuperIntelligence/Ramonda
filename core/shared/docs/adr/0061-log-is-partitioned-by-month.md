# The log is partitioned by month

Status: accepted

`events` is partitioned by month on `occurred_at`, with partitions created ahead of time. The chain crosses every partition.

A month moves to cold storage after a year (0042), with a grace month, and is dropped only when the ten-year retention ends. Detaching a partition is a metadata operation. Deleting a million rows from the one table that must not pause is not.

Rejected: one unpartitioned table, because the later migration happens on the hottest table; and exporting old events now, because there is no year-one data to export.

## Consequences

- Retention and cold tiering are the only operations that touch old events, and both are cheap on a partition.
- The chain resolves by sequence across partitions, so verification reads every surviving partition.
- A late event for a retired month is quarantined and alerted. The grace month makes that close to impossible; it exists so the failure is loud instead of silent.
- Once retention removes the oldest months, the chain is verifiable only from the oldest surviving event. A signed document still verifies against its signed head, but its history can no longer be replayed. That is the cost 0042 accepted.
