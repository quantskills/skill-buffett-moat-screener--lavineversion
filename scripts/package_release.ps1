[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,

    [string]$DemoPath
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$canonicalJson = Join-Path $projectRoot "output\screen-20251231-all-sh-sz-v12.json"
$productionDb = Join-Path $projectRoot "production\database.parquet"
$archivePrefix = "skill-buffett-moat-screener/"
$outputFullPath = [IO.Path]::GetFullPath($OutputPath)
$outputParent = Split-Path -Parent $outputFullPath

if (-not (Test-Path -LiteralPath $outputParent)) {
    throw "Output directory does not exist: $outputParent"
}
if (-not (Test-Path -LiteralPath $canonicalJson)) {
    throw "Canonical JSON not found: $canonicalJson"
}
if (-not (Test-Path -LiteralPath $productionDb)) {
    throw "Production database not found: $productionDb"
}
if ($DemoPath -and -not (Test-Path -LiteralPath $DemoPath)) {
    throw "Demo video not found: $DemoPath"
}

if (Test-Path -LiteralPath $outputFullPath) {
    Remove-Item -LiteralPath $outputFullPath
}

& git -C $projectRoot archive --format=zip --prefix=$archivePrefix --output=$outputFullPath HEAD
if ($LASTEXITCODE -ne 0) {
    throw "git archive failed"
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::Open($outputFullPath, [IO.Compression.ZipArchiveMode]::Update)
try {
    $nestedRoot = "${archivePrefix}${archivePrefix}"
    $nested = $archive.Entries | Where-Object { $_.FullName.StartsWith($nestedRoot) }
    if ($nested) {
        throw "nested duplicate project directory found in release package"
    }
    $artifacts = @(
        @{ Source = $canonicalJson; Entry = "${archivePrefix}output/screen-20251231-all-sh-sz-v12.json" },
        @{ Source = $productionDb; Entry = "${archivePrefix}production/database.parquet" }
    )
    if ($DemoPath) {
        $artifacts += @{ Source = [IO.Path]::GetFullPath($DemoPath); Entry = "${archivePrefix}demo.mp4" }
    }

    foreach ($artifact in $artifacts) {
        $existing = $archive.GetEntry($artifact.Entry)
        if ($null -ne $existing) {
            $existing.Delete()
        }
        [IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive,
            $artifact.Source,
            $artifact.Entry,
            [IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
    }
}
finally {
    $archive.Dispose()
}

Write-Output "Release package: $outputFullPath"
Write-Output "Canonical JSON: included"
Write-Output "Production Parquet: included"
Write-Output "Demo video: $(if ($DemoPath) { 'included' } else { 'not included' })"
