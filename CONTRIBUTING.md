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

1. Create your fork of `isard/isardvdi` repository.
2. Clone **your** fork.
3. Add the upstream remote:

```sh
git remote add upstream https://gitlab.com/isard/isardvdi.git
```

4. Make sure you have the latest changes:

```sh
git fetch upstream
```

5. Create a new branch:

```sh
git switch -c <name> upstream/main`
```

6. Work in this branch.
7. Commit your changes (no more than needed) and write a [good and descriptive commit message](https://www.freecodecamp.org/news/writing-good-commit-messages-a-practical-guide/) using [Conventional Commits](https://www.conventionalcommits.org) rules:

```
git add -p
git commit
```

8. Make sure you're on the latest `upstream` commit:

```sh
git fetch upstream && git rebase upstream/main
```

9. Test your rebased changes.
10. Push the branch to your remote:

```sh
git push
```

11. Create a Merge Request to the `main` branch of the `isard/isardvdi` repository. Please be descriptive in both the title and the description!
12. Wait for a review the changes to decide if it's ready for a release.
13. Make the required changes amenting your commits and push it:

```sh
git add -p
git commit
git rebase -i upstream/main
git push
```

  We need this push to only see your changes in gitlab interface.

14. If other work is added to main development, please, rebase your work, go to 8.
15. Done! Thanks! The GitLab CI will create the release, the tag and publish de Docker images! :)
