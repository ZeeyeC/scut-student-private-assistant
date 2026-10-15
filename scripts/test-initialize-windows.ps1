# No Pester or network required. Run with Windows PowerShell 5.1 or pwsh.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'initialize-windows.ps1')
$script:Failures = 0
$script:Passed = 0

function Assert-True($Value, [string]$Message) {
    if (-not $Value) { throw $Message }
}

function Assert-Throws([scriptblock]$Action, [string]$Pattern) {
    try { & $Action } catch {
        if ($_.Exception.Message -notmatch $Pattern) { throw }
        return
    }
    throw "Expected failure matching: $Pattern"
}

function Test-Case([string]$Name, [scriptblock]$Body) {
    $temporary = Join-Path ([IO.Path]::GetTempPath()) ('campus init ' + [guid]::NewGuid())
    New-Item -ItemType Directory -Path $temporary | Out-Null
    try {
        & $Body $temporary
        $script:Passed++
        Write-Host "PASS $Name"
    } catch {
        $script:Failures++
        Write-Host "FAIL ${Name}: $($_.Exception.Message)"
        Write-Host $_.ScriptStackTrace
    } finally {
        Remove-Item -LiteralPath $temporary -Recurse -Force
    }
}

function New-Fixture([string]$Root) {
    foreach ($path in @('backend/uv.lock', 'frontend/package-lock.json',
            'extension/package-lock.json', 'scripts/build-desktop.py', 'scripts/package-desktop.py',
            'config/scut-undergraduate-2026-10-14.json', '.env.example')) {
        $file = Join-Path $Root $path
        New-Item -ItemType Directory -Path (Split-Path $file) -Force | Out-Null
        [IO.File]::WriteAllText($file, '# test fixture')
    }
}

function New-Bundle([string]$Root) {
    $bundle = Join-Path $Root 'dist/desktop/CampusCompanion'
    foreach ($path in @('CampusCompanion.exe', '_internal/python312.dll',
            '_internal/frontend/dist/index.html',
            '_internal/extension/.output/chrome-mv3/manifest.json')) {
        $file = Join-Path $bundle $path
        New-Item -ItemType Directory -Path (Split-Path $file) -Force | Out-Null
        [IO.File]::WriteAllText($file, 'fixture')
    }
}

Test-Case 'Node version stays within the supported major' {
    Assert-True (Test-CampusNodeVersion 'v22.12.0') 'minimum rejected'
    Assert-True (Test-CampusNodeVersion 'v22.22.2') 'supported rejected'
    foreach ($version in @('v20.19.0', 'v22.11.0', 'v23.0.0', 'v24.0.0', 'garbage')) {
        Assert-True (-not (Test-CampusNodeVersion $version)) "accepted $version"
    }
}

Test-Case 'Architecture detects x64 shells and rejects unsupported native targets' {
    Assert-True ((Get-CampusArchitecture 'x86' 'AMD64') -eq 'x64') 'WOW64 not detected'
    Assert-Throws { Get-CampusArchitecture 'ARM64' '' } 'x64'
    Assert-Throws { Get-CampusArchitecture 'AMD64' 'ARM64' } 'x64'
    Assert-Throws { Get-CampusArchitecture 'x86' '' } 'x64'
}

Test-Case 'Checksum accepts official formats and rejects corrupt downloads' {
    param($root)
    $file = Join-Path $root 'archive.zip'
    [IO.File]::WriteAllText($file, 'download fixture')
    $hash = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
    Assert-CampusChecksum $file "$hash  archive.zip" 'archive.zip'
    Assert-CampusChecksum $file $hash 'archive.zip'
    Assert-Throws { Assert-CampusChecksum $file ('0' * 64) 'archive.zip' } 'checksum'
    Assert-Throws { Assert-CampusChecksum $file "$hash  different.zip" 'archive.zip' } 'checksum'
}

Test-Case 'Verified tool archives install nested and flat layouts with spaces and brackets' {
    param($root)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    foreach ($nested in @($false, $true)) {
        $payload = Join-Path $root ('payload-' + $nested)
        $binaryDirectory = if ($nested) { Join-Path $payload 'node-version-win-x64' } else { $payload }
        New-Item -ItemType Directory -Path $binaryDirectory -Force | Out-Null
        [IO.File]::WriteAllText((Join-Path $binaryDirectory 'node.exe'), 'verified binary')
        [IO.File]::WriteAllText((Join-Path $binaryDirectory 'npm.cmd'), 'companion file')
        $script:FixtureArchive = Join-Path $root ('fixture-' + $nested + '.zip')
        [IO.Compression.ZipFile]::CreateFromDirectory($payload, $script:FixtureArchive)
        $script:FixtureHash = (Get-FileHash -LiteralPath $script:FixtureArchive -Algorithm SHA256).Hash
        function Receive-CampusFile {
            param($Url, $Destination)
            if ($Url.EndsWith('.zip')) {
                Copy-Item -LiteralPath $script:FixtureArchive -Destination $Destination
            } else {
                [IO.File]::WriteAllText($Destination, $script:FixtureHash)
            }
        }
        $destination = Join-Path $root ('tools [local]/node-' + $nested)
        $installed = Install-CampusArchive 'https://example.test/node.zip' `
            'https://example.test/node.zip.sha256' $destination 'node.exe'
        Assert-True ((Get-Content -LiteralPath $installed -Raw) -eq 'verified binary') 'binary not installed'
        Assert-True (Test-Path -LiteralPath (Join-Path $destination 'npm.cmd')) 'companion files lost'
        $script:FixtureHash = '0' * 64
        Assert-Throws {
            Install-CampusArchive 'https://example.test/node.zip' `
                'https://example.test/node.zip.sha256' $destination 'node.exe'
        } 'checksum'
        Assert-True ((Get-Content -LiteralPath $installed -Raw) -eq 'verified binary') 'bad download replaced working tool'
    }
}

Test-Case 'Existing bundle starts offline without preparing tools' {
    param($root)
    New-Fixture $root
    New-Bundle $root
    function Get-CampusNode { throw 'unexpected tool installation' }
    function Get-CampusUv { throw 'unexpected tool installation' }
    function Start-CampusDesktop { param($Root) $script:Launched = $Root }
    $script:Launched = $null
    Initialize-CampusProject -Root $root
    Assert-True ($script:Launched -eq $root) 'bundle not launched'
    Assert-True (Test-Path (Join-Path $root '.env')) 'template not initialized'
    Assert-True (-not (Test-Path (Join-Path $root '.tools'))) 'offline path prepared tools'
}

Test-Case 'Fresh checkout builds once, preserves data, and restores environment' {
    param($root)
    $root = Join-Path $root ('[campus] ' + [char]0x8bfe + [char]0x95f4)
    New-Item -ItemType Directory -Path $root | Out-Null
    New-Fixture $root
    [IO.File]::WriteAllText((Join-Path $root '.env'), 'MODEL_API_KEY=test-only')
    [IO.File]::WriteAllText((Join-Path $root 'model.env'), 'MODEL_API_KEY=another-test-fixture')
    New-Item -ItemType Directory (Join-Path $root 'data') | Out-Null
    [IO.File]::WriteAllText((Join-Path $root 'data/campus.db'), 'private fixture')
    New-Item -ItemType Directory (Join-Path $root 'backups') | Out-Null
    [IO.File]::WriteAllText((Join-Path $root 'backups/fixture.zip'), 'private backup fixture')
    function Get-CampusArchitecture { return 'x64' }
    function Get-CampusNode { param($Tools, $Architecture) return (Join-Path $Tools 'node/node.exe') }
    function Get-CampusUv { param($Tools, $Architecture) return (Join-Path $Tools 'uv/uv.exe') }
    function Invoke-CampusNative {
        param($FilePath, $Arguments, $Step)
        $script:Calls += ,$Arguments
        if ($Arguments[0] -eq 'run') { New-Bundle (Get-Location).Path }
    }
    function Start-CampusDesktop { param($Root) $script:Launched = $Root }
    $oldPath = $env:PATH
    $oldPython = $env:UV_PROJECT_ENVIRONMENT
    $script:Calls = @()
    $script:Launched = $null
    Initialize-CampusProject -Root $root -NoLaunch
    Assert-True ($null -eq $script:Launched) 'NoLaunch still launched the application'
    Assert-True ($script:Calls.Count -eq 2) 'sync/build sequence missing'
    Assert-True ($script:Calls[0][0] -eq 'sync') 'sync must precede build'
    Assert-True ($script:Calls[0] -contains '--locked') 'dependency lock not used'
    Assert-True ($script:Calls[1] -contains '--no-sync') 'build resynced dependencies'
    Assert-True ($env:PATH -eq $oldPath) 'PATH not restored'
    Assert-True ($env:UV_PROJECT_ENVIRONMENT -eq $oldPython) 'uv environment not restored'
    Assert-True ((Get-Content -LiteralPath (Join-Path $root '.env') -Raw) -eq 'MODEL_API_KEY=test-only') 'key overwritten'
    Assert-True ((Get-Content -LiteralPath (Join-Path $root 'model.env') -Raw) -eq 'MODEL_API_KEY=another-test-fixture') 'model.env overwritten'
    Assert-True ((Get-Content -LiteralPath (Join-Path $root 'data/campus.db') -Raw) -eq 'private fixture') 'data overwritten'
    Assert-True ((Get-Content -LiteralPath (Join-Path $root 'backups/fixture.zip') -Raw) -eq 'private backup fixture') 'backup overwritten'
    Initialize-CampusProject -Root $root
    Assert-True ($script:Calls.Count -eq 2) 'repeated run rebuilt'
    Assert-True ($script:Launched -eq $root) 'second run did not launch'
}

Test-Case 'Explicit rebuild refreshes an existing bundle without overwriting settings' {
    param($root)
    New-Fixture $root
    New-Bundle $root
    [IO.File]::WriteAllText((Join-Path $root '.env'), 'MODEL_API_KEY=keep-this-fixture')
    function Get-CampusArchitecture { return 'x64' }
    function Get-CampusNode { param($Tools, $Architecture) return (Join-Path $Tools 'node/node.exe') }
    function Get-CampusUv { param($Tools, $Architecture) return (Join-Path $Tools 'uv/uv.exe') }
    function Invoke-CampusNative { $script:Calls++ }
    function Start-CampusDesktop { throw 'NoLaunch must not start application' }
    $script:Calls = 0
    Initialize-CampusProject -Root $root -Rebuild -NoLaunch
    Assert-True ($script:Calls -eq 2) 'explicit rebuild skipped'
    Assert-True ((Get-Content -LiteralPath (Join-Path $root '.env') -Raw) -eq 'MODEL_API_KEY=keep-this-fixture') 'settings overwritten'
}

Test-Case 'Dependency failure stops build and can be retried' {
    param($root)
    New-Fixture $root
    function Get-CampusArchitecture { return 'x64' }
    function Get-CampusNode { param($Tools, $Architecture) return (Join-Path $Tools 'node/node.exe') }
    function Get-CampusUv { param($Tools, $Architecture) return (Join-Path $Tools 'uv/uv.exe') }
    function Invoke-CampusNative {
        param($FilePath, $Arguments, $Step)
        $script:Calls++
        if ($script:FailSync) { throw 'dependency failed' }
        if ($Arguments[0] -eq 'run') { New-Bundle (Get-Location).Path }
    }
    function Start-CampusDesktop { throw 'must not launch on failure or NoLaunch' }
    $script:Calls = 0
    $script:FailSync = $true
    $oldPath = $env:PATH
    Assert-Throws { Initialize-CampusProject -Root $root -NoLaunch } 'dependency failed'
    Assert-True ($script:Calls -eq 1) 'continued after dependency failure'
    Assert-True ($env:PATH -eq $oldPath) 'environment leaked on failure'
    $script:FailSync = $false
    Initialize-CampusProject -Root $root -NoLaunch
    Assert-True (Test-CampusBundle $root) 'retry did not complete'
}

Test-Case 'Partial build is not mistaken for an installed application' {
    param($root)
    New-Fixture $root
    New-Item -ItemType Directory (Join-Path $root 'dist/desktop/CampusCompanion') -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $root 'dist/desktop/CampusCompanion/CampusCompanion.exe'), 'partial')
    Assert-True (-not (Test-CampusBundle $root)) 'partial bundle accepted'
    function Get-CampusArchitecture { return 'x64' }
    function Get-CampusNode { param($Tools, $Architecture) return (Join-Path $Tools 'node/node.exe') }
    function Get-CampusUv { param($Tools, $Architecture) return (Join-Path $Tools 'uv/uv.exe') }
    function Invoke-CampusNative { }
    function Start-CampusDesktop { throw 'must not launch incomplete build' }
    Assert-Throws { Initialize-CampusProject -Root $root -NoLaunch } 'incomplete'
}

Test-Case 'Failed rebuild cannot leave a seemingly ready bundle that skips retry' {
    param($root)
    New-Fixture $root
    New-Bundle $root
    function Get-CampusArchitecture { return 'x64' }
    function Get-CampusNode { param($Tools, $Architecture) return (Join-Path $Tools 'node/node.exe') }
    function Get-CampusUv { param($Tools, $Architecture) return (Join-Path $Tools 'uv/uv.exe') }
    function Invoke-CampusNative {
        param($FilePath, $Arguments, $Step)
        if ($Arguments[0] -eq 'run') { throw 'simulated interrupted packaging' }
    }
    Assert-Throws { Initialize-CampusProject -Root $root -Rebuild -NoLaunch } 'interrupted packaging'
    Assert-True (-not (Test-CampusBundle $root)) 'failed packaging still considered ready'
}

Test-Case 'Concurrent initialization fails before changing data' {
    param($root)
    New-Fixture $root
    $tools = Join-Path $root '.tools'
    New-Item -ItemType Directory $tools | Out-Null
    $lock = [IO.File]::Open((Join-Path $tools 'initialize.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    try {
        Assert-Throws { Initialize-CampusProject -Root $root -NoLaunch } 'already running'
        Assert-True (-not (Test-Path (Join-Path $root '.env'))) 'concurrent setup changed config'
    } finally { $lock.Dispose() }
}

Test-Case 'Failed downloads retry and do not leave a completed archive' {
    param($root)
    $script:Attempts = 0
    function Invoke-WebRequest {
        param($Uri, $OutFile, [switch]$UseBasicParsing, $TimeoutSec)
        $script:Attempts++
        [IO.File]::WriteAllText($OutFile, 'partial download')
        throw 'simulated network failure'
    }
    function Start-Sleep { }
    $destination = Join-Path $root 'archive.zip'
    Assert-Throws { Receive-CampusFile 'https://example.test/archive.zip' $destination } 'download'
    Assert-True ($script:Attempts -eq 3) 'download did not retry exactly three times'
    Assert-True (-not (Test-Path $destination)) 'partial download published'
    Assert-True (-not (Test-Path ($destination + '.partial'))) 'partial file left behind'
}

Test-Case 'Native nonzero exit is surfaced as a failed step' {
    $runtime = (Get-Process -Id $PID).Path
    Assert-Throws {
        Invoke-CampusNative $runtime @('-NoProfile', '-Command', 'exit 23') 'test child'
    } '23'
}

Test-Case 'Native stderr progress with exit zero is successful' {
    $runtime = (Get-Process -Id $PID).Path
    Invoke-CampusNative $runtime @('-NoProfile', '-Command',
        '[Console]::Error.WriteLine("fixture progress"); exit 0') 'test progress'
}

Test-Case 'Missing native executable is never considered success' {
    param($root)
    Assert-Throws {
        Invoke-CampusNative (Join-Path $root 'missing.exe') @() 'test missing executable'
    } 'not recognized|could not execute'
}

Write-Host "$script:Passed passed; $script:Failures failed"
if ($script:Failures) { exit 1 }
