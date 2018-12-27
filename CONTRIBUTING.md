# Contributing

## New feature

1. Fork the `isard-vdi/isard` repository
2. Clone **your** Isard fork and move  (if you already have your fork clonned, make sure you have the latest changes: `git fetch upstream`)
3. Add the upstream remote: `git remote add upstream https://github.com/isard-vdi/isard`

1. Initialize Git Flow: `git flow init`
2. Create the feature: `git flow feature start <feature name>` 
3. Work and commit it
4. Publish the feature branch: `git flow feature publish <feature name>`
5. Create a pull request from `your username/isard` `feature/<feature name>` to `isard-vdi/isard` `develop` branch



## New release

1. Clone the `isard-vdi/isard` repository
2. Create the release: `git flow release start X.X.X`
3. Publish the release branch: `git flow publish release X.X.X`
4. Create a pull request from the `isard-vdi/isard` `release/X.X.X` to `isard-vdi/isard` `master`
5. Update the Changelog, the `docker-compose.yml` file...
6. Merge the release to master
7. Create a new release to GitHub using as description the Changelog for the version
8. Pull the changes to the local `isard-vdi/isard` clone
9. Change to the new version tag: `git checkout X.X.X`
10. Build the Docker images and push them to Docker Hub

