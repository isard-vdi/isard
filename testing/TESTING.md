# Testing
1. Execute the testing docker-compose file
```sh
docker-compose -f docker-compose.yml -f testing/docker-compose.yml up -d
```
2. Run all the tests
```sh
docker-compose -f docker-compose.yml -f testing/docker-compose.yml exec isard-testing pytest testing
```
3. View the execution through selenium grid by browsing to [http://localhost:4444/ui/index.html#/sessions](http://localhost:4444/ui/index.html#/sessions) or connecting to the VNC viewer ports 6900 (chrome) or 6902 (firefox).

## Notes:
Tests can be selected with the -k option. Only tests which match the given substring expression will be executed (names are substring-matched against test names and their parent classes).

## Examples
- Testing by matching class name
```sh
docker-compose -f docker-compose.yml -f testing/docker-compose.yml exec isard-testing pytest testing -k 'Test_Frontend_Login_Logout'
```
- Testing by matching test name
```sh
docker-compose -f docker-compose.yml -f testing/docker-compose.yml exec isard-testing pytest testing -k 'test_frontend_login'
```