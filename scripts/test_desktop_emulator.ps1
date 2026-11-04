param(
    [Parameter(Mandatory=$true)][string]$Ucsim,
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
$flasher = Join-Path $repo 'flasher'
$runs = Join-Path $repo 'emulator/.runs'
New-Item -ItemType Directory -Force -Path $runs,(Join-Path $flasher 'build') | Out-Null
$testExe = Join-Path $flasher 'build/EmulatorTests.exe'
$sources = @('FileTool.cs','BootProtocol.cs','FlashWindow.cs','PinoutPage.cs','Theme.cs','EmulatorTests.cs') | ForEach-Object { Join-Path $flasher $_ }
& $compiler /nologo /target:exe /optimize+ /main:Xt660.EmulatorTests.Program "/out:$testExe" /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Web.Extensions.dll $sources
if ($LASTEXITCODE -ne 0) { throw 'Emulator test compilation failed' }
& $testExe (Join-Path $repo 'dist/yamaha-xt660-windows-v0.2.2') $runs $Python $Ucsim | Tee-Object -Variable result
$code = $LASTEXITCODE
[IO.File]::WriteAllText((Join-Path $runs 'desktop-emulator.log'), ($result -join "`n")+"`n", (New-Object Text.UTF8Encoding($false)))
if ($code -ne 0) { throw 'Desktop client against firmware emulator failed' }
