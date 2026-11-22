param([string]$Phrase = 'hey pika bot', [switch]$Awake)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
$audio = Join-Path $PSScriptRoot 'logs\wake-test.wav'
$speaker.SetOutputToWaveFile($audio)
$speaker.Speak($Phrase)
$speaker.Dispose()
& (Join-Path $PSScriptRoot 'pikabot\listen.ps1') -AudioFile $audio -Seconds 10 -Awake:$Awake
