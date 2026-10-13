# PreToolUse hook (matcher: Agent|Write|Edit). Windows PowerShell 5.1 compatible.
#  1. Agent: enforce SDLC stage order, artifact presence, and approval gates.
#  2. Write/Edit: block secret-like content in workflow artifacts and CHANGELOG.md.
# Fails closed: any unexpected error denies the call.

$stages = @(
    @{ Agent = 'requirements-analyst';    File = '01-requirements.md';   Gate = 'requirements'  },
    @{ Agent = 'architect';               File = '02-architecture.md';   Gate = $null           },
    @{ Agent = 'design-reviewer';         File = '03-design-review.md';  Gate = 'design-review' },
    @{ Agent = 'implementation-planner';  File = '04-plan.md';           Gate = 'plan'          },
    @{ Agent = 'implementer';             File = '05-implementation.md'; Gate = $null           },
    @{ Agent = 'code-reviewer';           File = '06-code-review.md';    Gate = $null           },
    @{ Agent = 'verifier';                File = '07-verification.md';   Gate = 'pre-pr'        },
    @{ Agent = 'release-preparer';        File = '08-pr.md';             Gate = $null           }
)

$secretPatterns = @(
    'AKIA[0-9A-Z]{16}',
    '-----BEGIN [A-Z ]*PRIVATE KEY-----',
    'gh[pousr]_[A-Za-z0-9]{36,}',
    '(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}',
    'xox[abprs]-[A-Za-z0-9-]{10,}',
    'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}',
    '(?i)bearer\s+[A-Za-z0-9._~+/=-]{20,}',
    '(?i)[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s:@]+@',
    '(?i)(password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)\s*[:=]\s*["'']?(?!<|\[|\*|\$|redacted)(?=[^\s"'']*[\d!@#%^&*+=/])[^\s"'']{8,}'
)

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

try {
    $in = [Console]::In.ReadToEnd() | ConvertFrom-Json
    $root = $env:CLAUDE_PROJECT_DIR
    if (-not $root) { $root = $in.cwd }

    if ($in.tool_name -eq 'Agent') {
        $name = [string]$in.tool_input.subagent_type
        $idx = -1
        for ($i = 0; $i -lt $stages.Count; $i++) {
            if ($stages[$i].Agent -eq $name) { $idx = $i }
        }
        if ($idx -lt 0) { exit 0 }   # not an SDLC stage agent

        $activePath = Join-Path $root 'workflow-runs\.active'
        if (-not (Test-Path -LiteralPath $activePath)) {
            Deny "No active workflow run. Start one with /sdlc-workflow <user story>."
        }
        $runId = (Get-Content -LiteralPath $activePath -Raw).Trim()
        if ($runId -notmatch '^[A-Za-z0-9_-]+$') { Deny "Invalid run id in workflow-runs/.active." }

        $runDir = Join-Path $root "workflow-runs\$runId"
        $statePath = Join-Path $runDir 'state.json'
        if (-not (Test-Path -LiteralPath $statePath)) { Deny "Missing $statePath." }
        $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json

        for ($k = 0; $k -lt $idx; $k++) {
            $f = Join-Path $runDir $stages[$k].File
            if (-not (Test-Path -LiteralPath $f) -or (Get-Item -LiteralPath $f).Length -eq 0) {
                Deny "Stage order violation: cannot run '$name' before '$($stages[$k].Agent)' has saved $($stages[$k].File)."
            }
            $gate = $stages[$k].Gate
            if ($gate -and ($state.approvals.$gate -ne $true)) {
                Deny "Approval required: checkpoint '$gate' has not been approved by the user, so '$name' cannot start."
            }
        }
        exit 0
    }

    if ($in.tool_name -eq 'Write' -or $in.tool_name -eq 'Edit') {
        $path = ([string]$in.tool_input.file_path) -replace '\\', '/'
        if ($path -notmatch '/workflow-runs/' -and $path -notmatch '(^|/)CHANGELOG\.md$') { exit 0 }

        $text = [string]$in.tool_input.content + "`n" + [string]$in.tool_input.new_string
        foreach ($p in $secretPatterns) {
            if ($text -cmatch $p) {   # -cmatch: case-sensitive unless the pattern sets (?i)
                Deny "Blocked: content written to '$path' looks like a secret or credential (pattern: $p). Replace it with <redacted> and retry."
            }
        }
    }
    exit 0
}
catch {
    Deny "workflow-guard error (failing closed): $($_.Exception.Message)"
}
