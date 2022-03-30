# Contributing

This file is going to be used to document de development process of IsardVDI, both for newcomers and old contributors!

## Development model

- IsardVDI is developed in a *rolling release* model. This means that every change done, is going to be a new version
- Uses [semver](https://semver.org/)
  + If the changes are a bugfix, increase the PATCH (x.x.X)
  + If the changes introduce a new feature, change the MINOR (x.X.x)
  + If some changes break the upgrading process, change the MAJOR (X.x.x)
- Does not provide support for old versions (e.g. if we have version 3.1.1 and 3.2.0 is out, there's never going to be version 3.1.2)

## Development workflow

### Review ready merge requests

Reviewing merge requests not marked as Draft is a priority task to unblock others work.

Tip: There is a merge request icon on top right menu of gitlab with the option "Review requests for you".

Tip: You can add `draft:=no` filter to merge request list.

Please, review priority merge requests first.

Tip: Merge request list can be sorted by priority.

Please mark merge request as Draft if you find something to do by author.

#### How to test a merge request

1. Find branch name:

```
Request to merge user_name:branch_name into main
```
2. Crop name to 63 characters and change non alfanumeric characters by `-`.
3. `cp isardvdi.cfg.example isardvdi.branch-name.cfg`
4. `echo DOCKER_IMAGE_TAG=branch-name >> isardvdi.branch-name.cfg`
5. `./build.sh`
6. `docker-compose -f docker-compose.branch-name.yml up -d`

### Deal with suggestions and questions of your merge requests

To get things done the priority is to deal with suggestions and questions of your merge requests. Mark the merge request as ready to get another review.

Tip: There is a merge request icon on top right menu of gitlab that points to merge request list that are assigned to you.

Please, work on priority merge resquests first.

Tip: Merge request list can be sorted by priority.

### Working on issues

Please, select priority issues first.

Tip: Issue list can be sorted by priority.

Please, work on an issue assigned to you. Other people should not work on issues assigned to you. If you cannot work on that issues unassign yourself and try to assign it to another person.

If you have no assigned issues, please work on issues assigned to nobody.

### Coding

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
