# Proxies

The **Proxies** page manages proxy groups, bulk import, health checks and profile assignments.

## Proxy groups

The left panel contains proxy groups:

- **New** creates a group.
- **Rename** renames the selected group.
- **Delete** removes the selected group.
- **All pools** shows proxies from every group.

## Bulk import

Use **Import List** / **Add Proxy** and paste proxies one per line.

Supported formats:

```text
ip:port:login:password
scheme://ip:port:login:password
scheme://user:pass@host:port
user:pass@host:port
```

Duplicates are ignored during bulk import.

## Proxy list actions

Each proxy row supports:

- select / unselect
- health-check one proxy
- edit name/value
- delete one proxy

Top actions:

- **Check Group** checks all visible proxies.
- **Release** clears assignment for selected proxies and removes proxy fields from assigned profiles.
- **Remove** deletes selected proxies from their pools.
- **Clear** clears selection.

## Statistics

The page shows:

- active proxies
- checking proxies
- failed proxies
- detected locations

Health checks store latency, status and geo metadata in the proxy pool.
