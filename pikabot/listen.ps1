param([string]$AudioFile = '', [int]$Seconds = 0, [switch]$Awake, [int]$ParentPid = 0)
$ErrorActionPreference = 'Stop'
if ($ParentPid) {
    Add-Type -TypeDefinition @'
using System;
using System.Diagnostics;
using System.Threading;
public static class PikabotParentWatch {
    public static void Start(int pid) {
        Process parent;
        try { parent = Process.GetProcessById(pid); }
        catch { Environment.Exit(0); return; }
        Thread watcher = new Thread(() => {
            try { parent.WaitForExit(); } catch { }
            Environment.Exit(0);
        });
        watcher.IsBackground = true;
        watcher.Start();
    }
}
'@
    [PikabotParentWatch]::Start($ParentPid)
}
Add-Type -AssemblyName System.Speech
$engine = $null
try {
    $culture = [System.Globalization.CultureInfo]::GetCultureInfo('en-US')
    $engine = [System.Speech.Recognition.SpeechRecognitionEngine]::new($culture)
    $choices = New-Object System.Speech.Recognition.Choices
    $choices.Add([string[]]@('hey pikabot','hey pika bot','hey peek a bot'))
    $builder = New-Object System.Speech.Recognition.GrammarBuilder
    $builder.Culture = [System.Globalization.CultureInfo]::GetCultureInfo('en-US')
    $builder.Append($choices)
    $wakeGrammar = New-Object System.Speech.Recognition.Grammar($builder)
    $dictation = New-Object System.Speech.Recognition.DictationGrammar
    $wakeGrammar.Enabled = -not $Awake
    $dictation.Enabled = [bool]$Awake
    $engine.LoadGrammar($wakeGrammar)
    $engine.LoadGrammar($dictation)
    $engine.EndSilenceTimeout = [TimeSpan]::FromSeconds(1.2)
    $engine.EndSilenceTimeoutAmbiguous = [TimeSpan]::FromSeconds(1.5)
    if ($AudioFile) { $engine.SetInputToWaveFile($AudioFile) }
    else { $engine.SetInputToDefaultAudioDevice() }
    @{kind='ready'} | ConvertTo-Json -Compress
    $until = if ($Seconds) { [DateTime]::UtcNow.AddSeconds($Seconds) } else { [DateTime]::MaxValue }
    while ([DateTime]::UtcNow -lt $until) {
        $result = $engine.Recognize([TimeSpan]::FromSeconds(1))
        if ($result) {
            @{kind='speech';text=$result.Text;confidence=$result.Confidence} | ConvertTo-Json -Compress
            if ($AudioFile) { break }
            if (-not $AudioFile) {
                $mode = [Console]::ReadLine()
                if ($null -eq $mode) { break }
                $dictation.Enabled = $mode -eq 'awake'
                $wakeGrammar.Enabled = -not $dictation.Enabled
            }
        }
        else { @{kind='heartbeat'} | ConvertTo-Json -Compress; if ($AudioFile) { break } }
    }
} catch {
    @{kind='error';message=$_.Exception.Message} | ConvertTo-Json -Compress
    exit 1
} finally { if ($engine) { $engine.Dispose() } }
