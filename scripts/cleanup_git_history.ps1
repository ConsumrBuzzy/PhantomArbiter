# Git History Cleanup Script for PhantomArbiter
# ═══════════════════════════════════════════════════════════════════════════
# IMPORTANT: This script removes sensitive data from git history.
# This is a DESTRUCTIVE operation - make a backup first!
# ═══════════════════════════════════════════════════════════════════════════

# STEP 1: Create a backup of your repository
# ───────────────────────────────────────────────────────────────────────────
git clone --mirror c:\Github\PhantomArbiter c:\Github\PhantomArbiter-backup

# STEP 2: Download BFG Repo-Cleaner (Recommended - faster than git filter-branch)
# ───────────────────────────────────────────────────────────────────────────
# Download from: https://rtyley.github.io/bfg-repo-cleaner/
# Or via Chocolatey: choco install bfg-repo-cleaner

# STEP 3: Create a file with the secrets to remove (secrets.txt)
# ───────────────────────────────────────────────────────────────────────────
# Save this content to a file called "secrets.txt":
#
#   ***REDACTED***
#   ***REDACTED***
#
# Add any other secrets you may have committed in the past.

# STEP 4: Run BFG to replace secrets with ***REMOVED***
# ───────────────────────────────────────────────────────────────────────────
cd c:\Github\PhantomArbiter
java -jar bfg.jar --replace-text secrets.txt

# STEP 5: Clean up the repository
# ───────────────────────────────────────────────────────────────────────────
git reflog expire --expire=now --all
git gc --prune=now --aggressive

# STEP 6: Force push to remote (CAUTION: This rewrites history!)
# ───────────────────────────────────────────────────────────────────────────
# If you have collaborators, coordinate with them before doing this.
git push --force

# ═══════════════════════════════════════════════════════════════════════════
# ALTERNATIVE: Using git-filter-repo (if BFG unavailable)
# ═══════════════════════════════════════════════════════════════════════════
# pip install git-filter-repo
#
# git filter-repo --replace-text secrets.txt --force
#
# ═══════════════════════════════════════════════════════════════════════════
# AFTER CLEANUP CHECKLIST:
# ═══════════════════════════════════════════════════════════════════════════
# [ ] Verify secrets are removed: git log -p --all -S "***REDACTED***"
# [ ] Revoke/rotate all exposed API keys
# [ ] Force push to all remotes
# [ ] Notify collaborators to re-clone the repository
# [ ] Delete any forks that may contain the old history
