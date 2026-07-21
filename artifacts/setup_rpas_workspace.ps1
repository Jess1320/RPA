$ErrorActionPreference = 'Stop'

$root = 'D:\RPAs_WORKSPACE'
$accounts = @(
    'ESSALUD\cenate.proyectosti',
    'ESSALUD\cenate.db01'
)

$dirs = @(
    $root,
    "$root\repos",
    "$root\docs",
    "$root\legacy-local-rpas",
    "$root\local-only",
    "$root\local-only\secrets",
    "$root\local-only\logs",
    "$root\local-only\scratch",
    "$root\notes"
)

foreach ($dir in $dirs) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

foreach ($account in $accounts) {
    & icacls $root /grant "${account}:(OI)(CI)F" /T | Out-Null
}

$result = Join-Path $root '_workspace_setup_result.txt'
@(
    "STATUS=OK",
    "ROOT=$root",
    "ACCOUNTS=$($accounts -join ', ')",
    "CREATED=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
) | Set-Content -LiteralPath $result -Encoding UTF8

Get-Content -LiteralPath $result
