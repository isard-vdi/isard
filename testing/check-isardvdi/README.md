# IsardVDI Check

```
docker run --rm --cap-add=NET_ADMIN -e HOST="https://localhost" -e USERNAME="admin" -e PASSWORD="IsardVDI" registry.gitlab.com/isard/isardvdi/check:main | tee isard-report.log
```