# One product, Packs as data, no forks

Every client is served by this one repository. What differs per client lives in a Pack: Sources, rules, Checks, outcomes, template and vocabulary. We never fork the repository per client, and we never copy a module into a "client variant".

Reason: a fork per client means each client's repo knows only its own security fixes, and the fifth client costs as much as the first. Change locality is the property we are buying — code that changes together must live together, and a client's differences are not changes to the platform.

The escape hatches are exactly two: a new Connector for a Source we cannot read, and a small compiled function on the approved list for a calculation that cannot be expressed as data. Both land in this repository and become available to every client afterwards.
