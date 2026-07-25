#Requires -Version 5.1
<#
.SYNOPSIS
  One-click start LMM WebHMI (PLC mode: Modbus TCP Server :502)
.EXAMPLE
  .\tools\start-webhmi.ps1
  .\tools\start-webhmi.ps1 -Mock
#>
param(
  [switch]$Mock,
  [int]$HttpPort = 8080,
  [string]$ModbusHost = '0.0.0.0',
  [int]$ModbusPort = 502,
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
  $env:MODBUS_HOST = $ModbusHost
  $env:MODBUS_PORT = "$ModbusPort"
  if ($Mock) {
    $env:MOCK_PLC = '1'
    Write-Host '[webhmi] mode=MOCK (no PLC)'
  } else {
    $env:MOCK_PLC = '0'
    Write-Host ("[webhmi] mode=PLC  Modbus Server {0}:{1}" -f $ModbusHost, $ModbusPort)
    Write-Host '[webhmi] PLC Master must target this host; FC03@1000 / FC16@1100 / len=64'
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
