# Contributing

This file is going to be used to document de development process of IsardVDI, both for newcomers and old contributors!

## Development model

- IsardVDI is developed in a *rolling release* model. This means that every change done, is going to be a new version
- Uses [semver](https://semver.org/)
  + If the changes are a bugfix, increase the PATCH (x.x.X)
  + If the changes introduce a new feature, change the MINOR (x.X.x)
  + If some changes break the upgrading process, change the MAJOR (X.x.x)
- Does not provide support for old versions (e.g. if we have version 3.1.1 and 3.2.0 is out, there's never going to be version 3.1.2)

## Example

Let's say we have found a bug and have a solution:

1. For the `isard/isardvdi` repository
2. Clone **your** fork
3. Add the upstream remote: `git remote add upstream https://gitlab.com/isard/isardvdi`
4. If you already have the clone, make sure you have the latest changes:

```sh
git checkout main
git pull upstream
```

5. Create a branch from there: `git checkout -b <name>` (please, pick a descriptive name!)
6. Work in this branch
7. Update the `CHANGELOG.md` and *commit* the changes. Write a [good and descriptive commit message](https://www.freecodecamp.org/news/writing-good-commit-messages-a-practical-guide/).
8. Make sure you're on the latest `upstream` commit: `git fetch upstream && git rebase upstream/main`
8. Push the branch to your remote: `git push`
9. Create a Merge Request to the `main` branch of the `isard/isardvdi` repository. Please be descriptive in both the title and the description!
10. Review the changes and decide it's ready for a release
11. Rebase again against the `upstream/main`. If there has been a release, use `git commit --amend` to edit the last commit and ensure the `CHANGELOG.md` is correct
12. Push to your fork and wait for someone to review the changes and merge it to `main`
13. Done! The GitLab CI will create the release, the tag and publish de Docker images! :)
