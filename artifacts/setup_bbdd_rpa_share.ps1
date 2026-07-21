$ErrorActionPreference = "Stop"

$shareName = "BBDD_RPA"
$sharePath = "D:\BBDD_RPA"
$account = "ESSALUD\cenate.db01"
$resultPath = Join-Path $sharePath "_share_setup_result.txt"

try {
    New-Item -ItemType Directory -Force -Path $sharePath | Out-Null

    $acl = Get-Acl -Path $sharePath
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        $account,
        "Modify",
        "ContainerInherit,ObjectInherit",
        "None",
        "Allow"
    )
    $acl.SetAccessRule($rule)
    Set-Acl -Path $sharePath -AclObject $acl

    $existing = Get-SmbShare -Name $shareName -ErrorAction SilentlyContinue
    if (-not $existing) {
        New-SmbShare -Name $shareName -Path $sharePath -ChangeAccess $account -Description "Publicacion temporal RPAs" | Out-Null
    } else {
        Grant-SmbShareAccess -Name $shareName -AccountName $account -AccessRight Change -Force | Out-Null
    }

    $share = Get-SmbShare -Name $shareName
    $access = Get-SmbShareAccess -Name $shareName | Out-String
    @(
        "STATUS=OK",
        "SHARE=\\$env:COMPUTERNAME\$shareName",
        "PATH=$($share.Path)",
        "ACCOUNT=$account",
        "TIME=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
        "",
        $access
    ) | Set-Content -Path $resultPath -Encoding UTF8
    exit 0
} catch {
    @(
        "STATUS=FAIL",
        "ERROR=$($_.Exception.Message)",
        "TIME=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    ) | Set-Content -Path $resultPath -Encoding UTF8
    exit 1
}
