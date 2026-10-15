# Windows PowerShell 5.1 compatible. Tools and caches stay inside this checkout.
[CmdletBinding()]
param(
    [switch]$NoLaunch,
    [switch]$Rebuild
)

$ErrorActionPreference = 'Stop'

function Test-CampusNodeVersion([string]$Version) {
    return ($Version.Trim() -match '^v?22\.(\d+)\.\d+$' -and [int]$Matches[1] -ge 12)
}

function Get-CampusArchitecture(
    [string]$Architecture = $env:PROCESSOR_ARCHITECTURE,
    [string]$NativeArchitecture = $env:PROCESSOR_ARCHITEW6432
) {
    if ($NativeArchitecture) { $Architecture = $NativeArchitecture }
    switch ($Architecture.ToUpperInvariant()) {
        'AMD64' { return 'x64' }
        default { throw 'Windows x64 is required. The locked desktop dependencies do not currently support ARM64 or 32-bit Windows initialization.' }
    }
}

function Receive-CampusFile([string]$Url, [string]$Destination) {
    if (([uri]$Url).Scheme -ne 'https') { throw 'Tool downloads require HTTPS.' }
    $partial = $Destination + '.partial'
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Write-Host "Downloading $([IO.Path]::GetFileName($Destination)) (attempt $attempt/3)..."
            Invoke-WebRequest -Uri $Url -OutFile $partial -UseBasicParsing -TimeoutSec 300
            Move-Item -LiteralPath $partial -Destination $Destination -Force
            return
        } catch {
            Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
            if ($attempt -eq 3) {
                throw "Tool download failed: $Url. Check your connection and run again. $($_.Exception.Message)"
            }
            Start-Sleep -Seconds $attempt
        }
    }
}

function Assert-CampusChecksum([string]$Archive, [string]$Checksums, [string]$ArchiveName) {
    $pattern = '(?im)^([a-f0-9]{64})\s+\*?' + [regex]::Escape($ArchiveName) + '\s*$'
    if ($Checksums -match $pattern -or $Checksums.Trim() -match '(?i)^([a-f0-9]{64})$') {
        $expected = $Matches[1]
        $actual = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash
        if ($actual -eq $expected) { return }
    }
    throw "SHA256 checksum verification failed for $ArchiveName. Run again to download a fresh copy."
}

function Install-CampusArchive(
    [string]$Url, [string]$ChecksumUrl, [string]$Destination, [string]$Executable
) {
    $parent = Split-Path $Destination
    $downloads = Join-Path $parent 'downloads'
    New-Item -ItemType Directory -Path $downloads -Force | Out-Null
    $name = [IO.Path]::GetFileName(([uri]$Url).AbsolutePath)
    $archive = Join-Path $downloads $name
    $checksum = $archive + '.sha256'
    Receive-CampusFile $Url $archive
    Receive-CampusFile $ChecksumUrl $checksum
    Assert-CampusChecksum $archive (Get-Content -LiteralPath $checksum -Raw) $name
    $staging = Join-Path $parent ('unpack-' + [guid]::NewGuid())
    try {
        Expand-Archive -LiteralPath $archive -DestinationPath $staging -Force
        $binary = Get-ChildItem -LiteralPath $staging -Recurse -File -Filter $Executable |
            Select-Object -First 1
        if (-not $binary) { throw "Downloaded archive is missing $Executable." }
        if (Test-Path -LiteralPath $Destination) {
            Remove-Item -LiteralPath $Destination -Recurse -Force
        }
        Move-Item -LiteralPath $binary.Directory.FullName -Destination $Destination
    } finally {
        if (Test-Path -LiteralPath $staging) {
            Remove-Item -LiteralPath $staging -Recurse -Force
        }
    }
    return (Join-Path $Destination $Executable)
}

function Get-CampusNode([string]$Tools, [string]$Architecture) {
    $destination = Join-Path $Tools 'node'
    $cached = Join-Path $destination 'node.exe'
    $system = Get-Command node.exe -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    $candidates = @($cached)
    if ($system) { $candidates += $system.Source }
    foreach ($candidate in $candidates) {
        if ((Test-Path -LiteralPath $candidate) -and
            (Test-Path -LiteralPath (Join-Path (Split-Path $candidate) 'npm.cmd'))) {
            try {
                $version = & $candidate --version 2>$null
                if ($LASTEXITCODE -eq 0 -and (Test-CampusNodeVersion "$version")) {
                    Write-Host "Using Node $version"
                    return $candidate
                }
            } catch { Write-Host 'Existing Node is unusable; preparing a private copy.' }
        }
    }
    $version = '22.23.3'
    $base = "https://nodejs.org/dist/v$version"
    return (Install-CampusArchive "$base/node-v$version-win-$Architecture.zip" `
        "$base/SHASUMS256.txt" $destination 'node.exe')
}

function Get-CampusUv([string]$Tools, [string]$Architecture) {
    $destination = Join-Path $Tools 'uv'
    $cached = Join-Path $destination 'uv.exe'
    $system = Get-Command uv.exe -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    $candidates = @($cached)
    if ($system) { $candidates += $system.Source }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            try {
                $version = & $candidate --version 2>$null
                if ($LASTEXITCODE -eq 0 -and "$version" -match '^uv (\d+\.\d+\.\d+)' -and
                    [version]$Matches[1] -ge [version]'0.11.19') {
                    Write-Host "Using $version"
                    return $candidate
                }
            } catch { Write-Host 'Existing uv is unusable; preparing a private copy.' }
        }
    }
    $target = if ($Architecture -eq 'arm64') { 'aarch64' } else { 'x86_64' }
    $base = 'https://releases.astral.sh/github/uv/releases/download/0.11.19'
    $url = "$base/uv-$target-pc-windows-msvc.zip"
    return (Install-CampusArchive $url "$url.sha256" $destination 'uv.exe')
}

function Invoke-CampusNative([string]$FilePath, [string[]]$Arguments, [string]$Step) {
    Write-Host $Step
    # Windows PowerShell represents native stderr as ErrorRecords. Progress on
    # stderr must not abort uv/npm; the process exit code determines success.
    $ErrorActionPreference = 'Continue'
    $global:LASTEXITCODE = $null
    & $FilePath @Arguments
    $code = $LASTEXITCODE
    if ($null -eq $code) { throw "$Step could not execute $FilePath. See .tools/initialize.log." }
    if ($code -ne 0) { throw "$Step failed (exit code $code). See .tools/initialize.log." }
}

function Test-CampusBundle([string]$Root, [switch]$IgnoreBuildState) {
    if (-not $IgnoreBuildState -and (Test-Path -LiteralPath (Join-Path $Root '.tools/build-incomplete'))) {
        return $false
    }
    $bundle = Join-Path $Root 'dist/desktop/CampusCompanion'
    foreach ($relative in @('CampusCompanion.exe', '_internal/python312.dll',
            '_internal/frontend/dist/index.html',
            '_internal/extension/.output/chrome-mv3/manifest.json')) {
        if (-not (Test-Path -LiteralPath (Join-Path $bundle $relative) -PathType Leaf)) {
            return $false
        }
    }
    return $true
}

function Initialize-CampusSettings([string]$Root) {
    $settings = Join-Path $Root '.env'
    if (-not (Test-Path -LiteralPath $settings)) {
        Copy-Item -LiteralPath (Join-Path $Root '.env.example') -Destination $settings
    }
}

function Start-CampusDesktop([string]$Root) {
    $executable = Join-Path $Root 'dist/desktop/CampusCompanion/CampusCompanion.exe'
    Start-Process -FilePath $executable -WorkingDirectory $Root `
        -ArgumentList @('--data-dir', ('"{0}"' -f $Root), '--project')
}

function Initialize-CampusProject([string]$Root, [switch]$NoLaunch, [switch]$Rebuild) {
    $Root = (Resolve-Path -LiteralPath $Root).Path
    if ((Test-CampusBundle $Root) -and -not $Rebuild) {
        Initialize-CampusSettings $Root
        if (-not $NoLaunch) { Start-CampusDesktop $Root }
        return
    }
    foreach ($relative in @('.env.example', 'backend/uv.lock', 'frontend/package-lock.json',
            'extension/package-lock.json', 'scripts/build-desktop.py', 'scripts/package-desktop.py',
            'config/scut-undergraduate-2026-10-14.json')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Root $relative) -PathType Leaf)) {
            throw "Missing $relative. Download and extract the complete repository first."
        }
    }
    $tools = Join-Path $Root '.tools'
    New-Item -ItemType Directory -Path $tools -Force | Out-Null
    try {
        $lock = [IO.File]::Open((Join-Path $tools 'initialize.lock'),
            [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    } catch { throw 'Initialization is already running. Wait for the other window to finish.' }
    $transcribing = $false
    $environment = @{}
    foreach ($name in @('PATH', 'UV_CACHE_DIR', 'UV_PYTHON_INSTALL_DIR',
            'UV_PYTHON_PREFERENCE', 'UV_PROJECT_ENVIRONMENT', 'UV_PYTHON_DOWNLOADS')) {
        $environment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    }
    $previousTls = [Net.ServicePointManager]::SecurityProtocol
    $locationPushed = $false
    try {
        Start-Transcript -LiteralPath (Join-Path $tools 'initialize.log') -Append | Out-Null
        $transcribing = $true
        Write-Host 'Preparing Campus Companion. The first run requires internet and may take several minutes.'
        Write-Host 'Your existing settings and personal data will be preserved.'
        Push-Location -LiteralPath $Root
        $locationPushed = $true
        [Net.ServicePointManager]::SecurityProtocol = $previousTls -bor [Net.SecurityProtocolType]::Tls12
        $architecture = Get-CampusArchitecture
        $runtime = Join-Path $tools 'windows'
        $node = Get-CampusNode $runtime $architecture
        $uv = Get-CampusUv $runtime $architecture
        $env:PATH = (Split-Path $node) + [IO.Path]::PathSeparator +
            (Split-Path $uv) + [IO.Path]::PathSeparator + $env:PATH
        $env:UV_CACHE_DIR = Join-Path $tools 'uv-cache'
        $env:UV_PYTHON_INSTALL_DIR = Join-Path $tools 'python'
        $env:UV_PYTHON_PREFERENCE = 'only-managed'
        $env:UV_PYTHON_DOWNLOADS = 'automatic'
        $env:UV_PROJECT_ENVIRONMENT = Join-Path $Root 'backend/.venv'
        $buildState = Join-Path $tools 'build-incomplete'
        [IO.File]::WriteAllText($buildState, 'Initialization has not completed. Run the launcher again.')
        Invoke-CampusNative $uv @('sync', '--project', 'backend', '--locked',
            '--python', '3.12', '--group', 'desktop') '[1/2] Installing Python 3.12 and locked dependencies'
        Invoke-CampusNative $uv @('run', '--project', 'backend', '--no-sync', 'python',
            'scripts/build-desktop.py') '[2/2] Building frontend, extension, and desktop application'
        if (-not (Test-CampusBundle $Root -IgnoreBuildState)) { throw 'The desktop build is incomplete. Run initialization again.' }
        Initialize-CampusSettings $Root
        Remove-Item -LiteralPath $buildState -Force
        Write-Host 'Initialization complete. Configure your own model connection in Settings.'
    } catch {
        Write-Host "Initialization failed: $($_.Exception.Message)"
        Write-Host 'Fix the reported problem, then double-click the launcher to retry.'
        throw
    } finally {
        foreach ($name in $environment.Keys) {
            [Environment]::SetEnvironmentVariable($name, $environment[$name], 'Process')
        }
        [Net.ServicePointManager]::SecurityProtocol = $previousTls
        if ($locationPushed) { Pop-Location }
        if ($transcribing) { Stop-Transcript | Out-Null }
        $lock.Dispose()
    }
    if (-not $NoLaunch) { Start-CampusDesktop $Root }
}

if ($MyInvocation.InvocationName -ne '.') {
    try {
        if ($env:OS -ne 'Windows_NT') { throw 'This initializer requires Windows. See docs/desktop.md for macOS.' }
        Initialize-CampusProject -Root (Split-Path $PSScriptRoot) -NoLaunch:$NoLaunch -Rebuild:$Rebuild
        exit 0
    } catch {
        Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}
