$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
$flasher = Join-Path $repo 'flasher'
$testExe = Join-Path $flasher 'build/ProtocolTests.exe'
$sources = @('FileTool.cs','BootProtocol.cs','FlashWindow.cs','PinoutPage.cs','Theme.cs','ProtocolTests.cs') | ForEach-Object { Join-Path $flasher $_ }
& $compiler /nologo /target:exe /optimize+ /main:Xt660.Tests.Program "/out:$testExe" /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Web.Extensions.dll $sources
if ($LASTEXITCODE -ne 0) { throw 'Protocol test compilation failed' }
& $testExe (Join-Path $repo 'dist/yamaha-xt660-windows-v0.2.2')
if ($LASTEXITCODE -ne 0) { throw 'Protocol tests failed' }
