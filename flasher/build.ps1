$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$out = Join-Path $PSScriptRoot 'build'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
if (!(Test-Path -LiteralPath $compiler)) { throw '.NET Framework C# compiler not found' }
$env:PYTHONUTF8 = '1'
python (Join-Path $repo 'scripts/build_flasher_resources.py')
if ($LASTEXITCODE -ne 0) { throw 'Resource build failed' }
$sources = @('FileTool.cs','BootProtocol.cs','FlashWindow.cs','PinoutWindow.cs','Theme.cs') | ForEach-Object { Join-Path $PSScriptRoot $_ }
& $compiler /nologo /target:winexe /optimize+ /platform:anycpu "/out:$out/XT660.FileTool.exe" /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Web.Extensions.dll "/resource:$repo/site/assets/yamaha-motor-logo.png,Xt660.Logo.png" "/resource:$out/connections.json,Xt660.Connections.json" "/resource:$repo/site/assets/fonts/Barlow-Regular.ttf,Xt660.Barlow-Regular.ttf" "/resource:$repo/site/assets/fonts/Barlow-SemiBold.ttf,Xt660.Barlow-SemiBold.ttf" "/resource:$repo/site/assets/fonts/BarlowCondensed-ExtraBoldItalic.ttf,Xt660.BarlowCondensed-ExtraBoldItalic.ttf" $sources
if ($LASTEXITCODE -ne 0) { throw 'Compilation failed' }
