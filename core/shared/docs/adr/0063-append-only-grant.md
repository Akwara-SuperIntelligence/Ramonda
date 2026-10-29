# The application can append and read the log, never change it

Status: accepted

The role that writes `events` holds `INSERT` and `SELECT` only. `UPDATE` and `DELETE` are revoked, and a trigger refuses both even for a role that somehow holds them. Detaching a partition belongs to the retention role alone.

The hash chain (0055) proves a change after the fact. It does not prevent one. The grant and the trigger are what make "an event is never updated or deleted" (0031) a property of the database rather than a habit of the application.

## Consequences

- A correction is a new event, never an edit.
- A retention deletion is a partition detach, performed by a role the application does not hold.
- The grant is part of the migration, so a fresh deployment and an old one carry the same lock.
