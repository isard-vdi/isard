# IsardVDI Check

```
docker run --rm --cap-add=NET_ADMIN -e HOST="https://localhost" -e USERNAME="admin" -e PASSWORD="IsardVDI" registry.gitlab.com/isard/isardvdi/check:main | tee isard-report.log
```

> Other interesting variables
> - `FAIL_SELF_SIGNED`: fails the check if a self signed certificate is found
> - `FAIL_MAINTENANCE_MODE`: fails if the maintenance mode is enabled
