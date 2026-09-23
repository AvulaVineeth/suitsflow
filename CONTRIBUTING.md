# Development workflow

Use short-lived feature branches from the latest `main`. Use descriptive prefixes:
`feat/`, `fix/`, `docs/`, or `chore/`. Keep `main` deployable; a permanent integration
branch is unnecessary until releases require a separate stabilization period.

1. Fetch `origin`, switch to `main`, and fast-forward it to `origin/main`.
2. Create a branch for one cohesive change and add meaningful tests.
3. Run Ruff formatting/lint, mypy, and the full PostgreSQL integration suite described
   in the README. Review migrations and their downgrade behavior.
4. Commit and push the feature branch. CI runs on feature pushes and pull requests.
5. Prefer a pull request into `main`, with passing checks and review before merging.
   When the repository owner explicitly authorizes a direct merge, use a normal
   fast-forward push after checks; never bypass branch protection or force-push `main`.
6. Start the next independent feature from the updated `main`.

Squash merging changes commit ancestry. If dependent branches exist, rebase only
their unmerged commits onto the updated `main` before opening the next pull request.
Use an explicit force-with-lease when updating a rebased feature branch, after
checking that the remote has no collaborator changes. Prefer finishing and merging
one slice before creating dependent branches.

Repository protection should require CI and prevent force pushes to `main`. These
settings are configured on GitHub; documenting them does not enable them.
