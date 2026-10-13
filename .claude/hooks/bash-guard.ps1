# PreToolUse hook for Bash. Windows PowerShell 5.1 compatible. Fails closed.
#  - No -Role (settings.json, all Bash calls): block publishing, Git remote/config writes, and reading .env* files.
#  - -Role review (code-reviewer frontmatter): allow only read-only git inspection commands.
#  - -Role verify (verifier frontmatter): block commands that modify files, Git state, or dependencies (best effort).
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

try {
    $in = [Console]::In.ReadToEnd() | ConvertFrom-Json
    if ($in.tool_name -ne 'Bash') { exit 0 }
    $cmd = [string]$in.tool_input.command

    # ---- Global rules -------------------------------------------------------
    if ($cmd -match ($git + 'push\b')) {
        Deny "Blocked: nothing may be pushed in this workflow."
    }
    if ($cmd -match ($git + 'remote\s+(add|set-url|set-head|rename|remove|rm|prune|update)\b')) {
        Deny "Blocked: Git remotes must not be changed in this workflow."
    }
    if ($cmd -match '(?i)(^|[;&|(\s])gh(\.exe)?(\s|$)') {
        Deny "Blocked: the GitHub CLI is not allowed in this workflow (no pull requests are opened)."
    }
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
