# Branch Protection Setup

This document describes the branch protection rules that should be configured for the `master` branch.

## Setup Instructions

1. Go to GitHub repository settings
2. Navigate to **Settings** → **Branches** → **Add rule**
3. Configure the following settings:

## Branch Protection Rules for `master`

### Branch Name Pattern
```
master
```

### Protection Settings

#### Required Status Checks
✅ **Require status checks to pass before merging**
- ✅ Require branches to be up to date before merging

**Required status checks:**
- `lint`
- `test`
- `smoke-tests`
- `build-status`

#### Pull Request Requirements
✅ **Require pull request reviews before merging**
- Required approving reviews: 1
- ✅ Dismiss stale pull request approvals when new commits are pushed
- ✅ Require review from Code Owners (if CODEOWNERS file exists)

#### Additional Settings
✅ **Require conversation resolution before merging**
✅ **Require linear history**
✅ **Include administrators** (recommended for consistency)

## Alternative: Automated Setup

If you prefer to set up branch protection via GitHub API, use this script:

```bash
# Set your GitHub token
export GITHUB_TOKEN="your_github_token_here"
export REPO_OWNER="outwareai"
export REPO_NAME="boss-workflow"

curl -X PUT \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/$REPO_OWNER/$REPO_NAME/branches/master/protection \
  -d '{
    "required_status_checks": {
      "strict": true,
      "contexts": ["lint", "test", "smoke-tests", "build-status"]
    },
    "enforce_admins": true,
    "required_pull_request_reviews": {
      "dismissal_restrictions": {},
      "dismiss_stale_reviews": true,
      "require_code_owner_reviews": false,
      "required_approving_review_count": 1,
      "require_last_push_approval": false
    },
    "restrictions": null,
    "required_linear_history": true,
    "allow_force_pushes": false,
    "allow_deletions": false,
    "required_conversation_resolution": true
  }'
```

## Verification

After setting up, verify by:
1. Creating a test branch
2. Making a change
3. Opening a PR
4. Confirming that:
   - CI pipeline runs automatically
   - All required checks appear in the PR
   - Merge button is disabled until all checks pass
   - Cannot merge without review

## Troubleshooting

### Status checks not appearing
- Ensure the workflow files are on the `master` branch
- Check that workflow names match the required status check names
- Verify GitHub Actions is enabled for the repository

### Cannot merge even with passing checks
- Verify all required status checks are listed in branch protection
- Ensure branch is up to date with base branch
- Check that reviews are approved if required

### Want to bypass for emergency
1. Temporarily disable "Include administrators" if you're an admin
2. Make the emergency merge
3. Re-enable the protection immediately after
