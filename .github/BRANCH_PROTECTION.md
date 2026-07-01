# Branch Protection Setup — main

The `.github/workflows/test.yml` workflow runs `Backend pytest` on every PR and
push to `main`. Make it a **required check** so PRs cannot be merged unless
the suite passes.

You only need to do this once, after pushing the workflow file to GitHub.

---

## Option A — GitHub web UI (recommended, ~30 seconds)

1. Push the current codebase to GitHub via the **Save to GitHub** button in
   the Emergent chat input.
2. Open your repo → **Settings** → **Branches** (left sidebar).
3. Under *Branch protection rules*, click **Add branch protection rule** (or
   *Add rule* on older UIs).
4. Fill in the form:
   - **Branch name pattern**: `main`
   - Check **Require a pull request before merging**
   - Check **Require status checks to pass before merging**
     - Check **Require branches to be up to date before merging** (optional
       but recommended — forces PRs to rebase onto latest `main`)
     - In the search box under *Status checks that are required*, type
       `Backend pytest` and select it from the dropdown.
     - Also add `Backend lint (ruff)` if you want lint failures to block too.
     - *Tip*: If the checks don't appear in the dropdown, open one PR first
       so GitHub sees the checks running once — then they show up here.
   - Check **Require conversation resolution before merging** (optional; nice-to-have)
   - Check **Do not allow bypassing the above settings** (this covers admins too)
5. Click **Create** at the bottom.

That's it. Try opening a PR that intentionally breaks a test — GitHub will
now refuse to merge until the check goes green.

---

## Option B — GitHub CLI (`gh`) one-liner

If you have the [GitHub CLI](https://cli.github.com/) installed and
authenticated (`gh auth login`), you can set this from the terminal:

```bash
gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  "/repos/{OWNER}/{REPO}/branches/main/protection" \
  -f "required_status_checks[strict]=true" \
  -f "required_status_checks[contexts][]=Backend pytest" \
  -f "required_status_checks[contexts][]=Backend lint (ruff)" \
  -F "enforce_admins=true" \
  -f "required_pull_request_reviews[required_approving_review_count]=0" \
  -F "restrictions=null"
```

Replace `{OWNER}` and `{REPO}` with your GitHub user/org and repo name. Set
`required_approving_review_count` to `1` if you want to also require a
reviewer sign-off (recommended for team repos).

---

## Verifying it worked

- Open the repo on GitHub → **Insights** → **Rules** → you should see one
  active rule targeting `main`.
- Open a test PR. In the **Merge** area of the PR page, GitHub should show
  a checklist including *"All checks have passed"* / *"Backend pytest —
  Waiting to run"* etc.
- If GitHub Actions shows the workflow ran but the check isn't listed in
  the required-checks dropdown, refresh the branch protection settings and
  re-add the check name (it now appears in the autocomplete).

---

## Notes / gotchas

- The status-check name must **match the job's `name:` field exactly** — for
  our workflow that's `Backend pytest` and `Backend lint (ruff)`. If you
  rename a job in `test.yml`, update the required check name here too.
- Direct pushes to `main` are still allowed by default. To also block those,
  either check *Include administrators* in the UI, or use a workflow that
  blocks pushes outside of PRs.
- Emergent's **Save to GitHub** flow pushes commits to `main` directly (not
  via PR). If you enable *Include administrators*, that push will be blocked
  by branch protection. Two options:
    1. Set up an Emergent → feature-branch → PR → main flow (safer, adds
       review latency).
    2. Leave *Include administrators* unchecked so the Emergent bot can push
       straight to main while human PRs still go through the checks.
  Recommendation: for a solo project, option 2 is pragmatic. For a team,
  option 1 is safer.
