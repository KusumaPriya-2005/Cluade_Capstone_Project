# PreToolUse hook for Bash. Windows PowerShell 5.1 compatible. Fails closed.
#  - No -Role (settings.json, all Bash calls):
#      * Publishing (git push, git remote add, gh pr create) is allowed ONLY for the repository in
#        .claude/publish.json, only after the active run's 'pre-pr' checkpoint is approved, never with
#        force/delete/--all/tags, and never chained with other commands.
#      * Git config writes and reading .env* files are blocked.
#  - -Role review (code-reviewer frontmatter): allow only read-only git inspection commands.
#  - -Role verify (verifier frontmatter): block commands that modify files, Git state, or dependencies (best effort).
#  - -Role nopublish (implementer and release-preparer frontmatter): no publishing commands at all.
param([string]$Role = '')

function Deny([string]$reason) {
    $out = @{
        hookSpecificOutput = @{
            hookEventName            = 'PreToolUse'
            permissionDecision       = 'deny'
            permissionDecisionReason = $reason
        }
    }
    Write-Output ($out | ConvertTo-Json -Depth 5 -Compress)
    exit 0
}

# "git" followed by optional global options (-c k=v, -C dir, --flag) and a space.
$git = '(?i)\bgit(\s+(-[cC]\s+\S+|--[\w-]+(=\S+)?))*\s+'

function Normalize-Url([string]$u) {
    return (($u.Trim().TrimEnd('/')) -replace '\.git$', '').ToLowerInvariant()
}

function Get-GitExe {
    $c = Get-Command git -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    foreach ($p in @("$env:ProgramFiles\Git\cmd\git.exe", "${env:ProgramFiles(x86)}\Git\cmd\git.exe")) {
        if (Test-Path -LiteralPath $p) { return $p }
    }
    return $null
}

# Returns a problem description, or $null when the active run has an approved 'pre-pr' checkpoint.
function Get-PublishGateProblem([string]$root) {
    $active = Join-Path $root 'workflow-runs\.active'
    if (-not (Test-Path -LiteralPath $active)) { return 'no active workflow run' }
    $runId = (Get-Content -LiteralPath $active -Raw).Trim()
    if ($runId -notmatch '^[A-Za-z0-9_-]+$') { return 'invalid run id' }
    $sp = Join-Path $root "workflow-runs\$runId\state.json"
    if (-not (Test-Path -LiteralPath $sp)) { return 'missing state.json' }
    $st = Get-Content -LiteralPath $sp -Raw | ConvertFrom-Json
    if ($st.approvals.'pre-pr' -ne $true) { return "checkpoint 'pre-pr' is not approved" }
    return $null
}

try {
    $in = [Console]::In.ReadToEnd() | ConvertFrom-Json
    if ($in.tool_name -ne 'Bash') { exit 0 }
    $cmd = [string]$in.tool_input.command
    $root = $env:CLAUDE_PROJECT_DIR
    if (-not $root) { $root = $in.cwd }

    # ---- Publishing rules ---------------------------------------------------
    $isPush   = $cmd -match ($git + 'push\b')
    $isRemote = $cmd -match ($git + 'remote\s+(add|set-url|set-head|rename|remove|rm|prune|update)\b')
    $isGh     = $cmd -match '(?i)(^|[;&|(\s])gh(\.exe)?(\s|$)'

    if ($isPush -or $isRemote -or $isGh) {
        if ($Role -ne '') {
            Deny "Blocked for this agent: publishing commands (git push, git remote changes, gh) are run only by the Orchestrator."
        }
        $readOnlyGh = $cmd -match '(?i)^\s*gh(\.exe)?\s+(--version|auth\s+status)\s*$'
        if (-not $readOnlyGh) {
            $cfgPath = Join-Path $root '.claude\publish.json'
            if (-not (Test-Path -LiteralPath $cfgPath)) {
                Deny "Blocked: publishing is not configured (.claude/publish.json is missing)."
            }
            $cfg = Get-Content -LiteralPath $cfgPath -Raw | ConvertFrom-Json
            $problem = Get-PublishGateProblem $root
            if ($problem) {
                Deny "Blocked: publishing needs an approved pre-PR checkpoint in an active run ($problem)."
            }
            if ($cmd -match '[;&|`]' -or $cmd -match '\$\(') {
                Deny "Blocked: run each publishing command on its own, without chaining, pipes, or substitutions."
            }
            $slug = [regex]::Escape([string]$cfg.repo_slug)
            $base = [regex]::Escape([string]$cfg.base_branch)

            if ($isPush) {
                $re = '^\s*git\s+push(\s+(-u|--set-upstream))?\s+origin\s+(' + $base + '|feature/[A-Za-z0-9._/-]+)\s*$'
                if ($cmd -cnotmatch $re) {
                    Deny "Blocked: only 'git push [-u] origin <$($cfg.base_branch) or feature/...>' is allowed. Force, delete, --all, tags, refspecs and other remotes are not."
                }
                $gx = Get-GitExe
                if (-not $gx) { Deny "Blocked: cannot find git to verify the origin remote." }
                $origin = [string](& $gx -C $root remote get-url origin 2>$null)
                if (-not $origin -or (Normalize-Url $origin) -ne (Normalize-Url ([string]$cfg.repo_url))) {
                    Deny "Blocked: remote 'origin' is missing or does not point at $($cfg.repo_slug)."
                }
            }
            elseif ($isRemote) {
                if ($cmd -notmatch '^\s*git\s+remote\s+add\s+origin\s+(\S+)\s*$' -or (Normalize-Url $Matches[1]) -ne (Normalize-Url ([string]$cfg.repo_url))) {
                    Deny "Blocked: only 'git remote add origin $($cfg.repo_url)' is allowed."
                }
            }
            else {
                $isCreate = ($cmd -match '(?i)^\s*gh(\.exe)?\s+pr\s+create\b') -and
                            ($cmd -match ('(?i)--repo\s+' + $slug + '(\s|$)')) -and
                            ($cmd -cmatch ('--base\s+' + $base + '(\s|$)'))
                $isView = ($cmd -match '(?i)^\s*gh(\.exe)?\s+pr\s+(view|list)\b') -and
                          ($cmd -match ('(?i)--repo\s+' + $slug + '(\s|$)'))
                if (-not ($isCreate -or $isView)) {
                    Deny "Blocked: only 'gh auth status', 'gh pr create --repo $($cfg.repo_slug) --base $($cfg.base_branch) ...' and 'gh pr view|list --repo $($cfg.repo_slug)' are allowed."
                }
            }
        }
    }

    # ---- Other global rules -------------------------------------------------
    if ($cmd -match ($git + 'config\b(?<args>[^;&|]*)')) {
        $tokens = @($Matches['args'] -split '\s+' | Where-Object { $_ })
        $writeFlag = @($tokens | Where-Object { $_ -match '^(--(global|system|local|worktree|file|add|unset|unset-all|replace-all|edit|rename-section|remove-section)|-e|-f)$' }).Count -gt 0
        $positional = @($tokens | Where-Object { $_ -notmatch '^-' }).Count
        if ($writeFlag -or $positional -ge 2) {
            Deny "Blocked: Git config must not be changed. Reading values (git config user.name) is allowed."
        }
    }
    if ($cmd -match '(?i)(^|[\s/\\"''=<])\.env(\.[\w.-]+)?(?=$|[\s"'';|&>])') {
        Deny "Blocked: .env* files may contain secrets and must not be accessed."
    }

    # ---- Role: code-reviewer ------------------------------------------------
    if ($Role -eq 'review') {
        if ($cmd -match '[;&|<>`]' -or $cmd -match '\$\(' -or $cmd -match '--output') {
            Deny "Blocked for code-reviewer: use a single read-only git command without pipes, redirects, or chaining. Use Read and Grep for files."
        }
        if ($cmd -notmatch '(?i)^\s*git(\s+--no-pager)?\s+(status|diff|log|show|ls-files|rev-parse|blame|diff-tree|cat-file|describe|shortlog|branch\s+(--show-current|--list|-v|-vv|-a))(\s|$)') {
            Deny "Blocked for code-reviewer: only read-only git inspection (status, diff, log, show, ls-files, rev-parse, blame) is allowed."
        }
    }

    # ---- Role: verifier -----------------------------------------------------
    if ($Role -eq 'verify') {
        $clean = $cmd -replace '2>&1', '' -replace '&>\s*/dev/null', '' -replace '2?>\s*/dev/null', '' -replace '2?>\s*NUL\b', ''
        if ($clean -match '>') {
            Deny "Blocked for verifier: output redirection to files is not allowed."
        }
        $mutating = @(
            @{ N = 'file delete/move/copy/create'; P = '(?i)(^|[;&|(\s])(rm|rmdir|del|erase|mv|move|cp|copy|touch|mkdir|ln|tee|truncate|chmod|chown|dd)(\.exe)?(\s|$)' },
            @{ N = 'in-place edit';                P = '(?i)\bsed\s+(-\w*i|--in-place)' },
            @{ N = 'Git state change';             P = ($git + '(add|commit|checkout|switch|reset|restore|clean|stash|merge|rebase|cherry-pick|revert|apply|am|mv|rm|tag|init|clone|pull|fetch|worktree|submodule|gc|prune|branch\s+-[dDmMcC])\b') },
            @{ N = 'dependency install';           P = '(?i)\b(npm|yarn|pnpm|bun)\s+(install|i|add|ci|update|upgrade|uninstall|remove|link)\b|\bpip3?\s+(install|uninstall)\b|\b(winget|choco|scoop|apt|apt-get|brew)\s' },
            @{ N = 'download';                     P = '(?i)(^|[;&|(\s])(curl|wget|iwr|irm)(\.exe)?(\s|$)|Invoke-(WebRequest|RestMethod)' },
            @{ N = 'file cmdlet or nested shell';  P = '(?i)\b(Set|Add|Clear)-Content\b|\b(Out-File|Remove-Item|Move-Item|Copy-Item|New-Item|Rename-Item)\b|(^|[;&|(\s])(powershell|pwsh|cmd)(\.exe)?(\s|$)' }
        )
        foreach ($m in $mutating) {
            if ($cmd -match $m.P) {
                Deny "Blocked for verifier (read-only role): $($m.N). Run checks only; do not modify files, Git state, or dependencies."
            }
        }
    }
    exit 0
}
catch {
    Deny "bash-guard error (failing closed): $($_.Exception.Message)"
}
