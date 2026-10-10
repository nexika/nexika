---
name: setup
description: Prepare a GitHub repository for amin - confirm the detected projects and versions, create the change-notes folder, add the CI rule that every PR needs a change note, and create the no-changelog label. Use when the user says "set up amin", "amin setup", or before the first /amin:release in a repo.
---

# Set up amin in this repository

The amin helper command is printed in the session note ("amin helper: python3 .../bin/amin");
below it is written `amin`. Change nothing without the user's approval, and make every change
on a branch with a pull request (never commit to the default branch).

1. **Projects.** Run `amin projects`. Show what was detected: name, version, version file,
   changelog file, tag format. If nothing was detected or something is wrong, write
   `.amin.json` with the user:
   ```json
   {"projects": [{"name": "api", "path": "src/Api", "version_files": ["src/Api/Api.csproj"]}]}
   ```
   (optional per project: `"changelog"`, `"tag": "{name}-v{version}"`).
   If `projects` says the changelog file is missing and `gh release list --limit 5` shows
   releases, ask whether the release notes live in GitHub releases; if so, propose
   `"changelog": "github"` for that project (amin then writes no changelog file).
2. **Notes folder.** If `changelog.d/README.md` is missing, create it explaining the rule:
   one file per change, `changelog.d/<project>/<id>.<type>.md` (single project:
   `changelog.d/<id>.<type>.md`), types breaking / added / changed / deprecated / removed /
   fixed / security, text written for users.
3. **CI rule** (GitHub Actions). Propose adding this job to the main workflow, plus
   `labeled, unlabeled` to the `pull_request` trigger types and the job to any "all checks
   passed" gate:
   ```yaml
   changelog:
     name: change notes
     if: github.event_name == 'pull_request'
     runs-on: ubuntu-latest
     steps:
       - uses: actions/checkout@v5   # use the version the workflow already uses
         with: {fetch-depth: 0}
       - name: Each changed project has a change note
         env:
           BASE: ${{ github.base_ref }}
           LABELS: ${{ join(github.event.pull_request.labels.*.name, ',') }}
         # run the base branch's copy, so a PR can't loosen the rule it is checked by
         run: |
           mkdir -p "$RUNNER_TEMP/amin-base"
           git archive "origin/$BASE" <path to amin> | tar -x -C "$RUNNER_TEMP/amin-base"
           python3 "$RUNNER_TEMP/amin-base/<path to amin>/bin/amin" check-fragment --base "origin/$BASE" --labels "$LABELS"
   ```
   If amin is not vendored in the repo, ask where the team wants the helper to come from.
4. **Label.** Offer `gh label create no-changelog --description "PR needs no change note"`.
5. Open the PR with these changes and tell the user to review and merge it.
