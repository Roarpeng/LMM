#Requires -Version 5.1
<#
.SYNOPSIS
  One-click start LMM WebHMI (Gateway Modbus master -> PLC slave)
.EXAMPLE
  .\tools\start-webhmi.ps1
  .\tools\start-webhmi.ps1 -Mock
  .\tools\start-webhmi.ps1 -PlcHost 192.168.1.88 -PlcPort 502
#>
param(
  [switch]$Mock,
  [int]$HttpPort = 8080,
  [string]$PlcHost = '192.168.1.88',
  [int]$PlcPort = 502,
  [int]$PlcUnitId = 1,
  [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Gateway = Join-Path $Root 'gateway'

if (-not (Test-Path (Join-Path $Gateway 'package.json'))) {
  Write-Error "gateway/package.json not found under $Root"
}

Push-Location $Gateway
try {
  if (-not (Test-Path 'node_modules')) {
    Write-Host '[webhmi] npm install ...'
    npm install
  }

  $env:HTTP_PORT = "$HttpPort"
  $env:WS_PORT = "$HttpPort"
  $env:PLC_HOST = $PlcHost
  $env:PLC_PORT = "$PlcPort"
  $env:PLC_UNIT_ID = "$PlcUnitId"
  if ($Mock) {
    $env:MOCK_PLC = '1'
    Write-Host '[webhmi] mode=MOCK (no PLC)'
  } else {
    $env:MOCK_PLC = '0'
    Write-Host ("[webhmi] mode=PLC  Gateway MASTER -> PLC SLAVE {0}:{1} unit={2}" -f $PlcHost, $PlcPort, $PlcUnitId)
    Write-Host '[webhmi] FC16@4096(0x1000) write cmd / FC03@4352(0x1100) read status'
  }

  $url = "http://127.0.0.1:${HttpPort}/"
  Write-Host "[webhmi] open $url"
  if (-not $NoBrowser) {
    Start-Process $url
  }

  Write-Host '[webhmi] Ctrl+C to stop Gateway'
  node server.js
} finally {
  Pop-Location
}
