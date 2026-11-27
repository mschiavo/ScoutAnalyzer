[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[A-Za-z0-9_][A-Za-z0-9_.-]*(?:@[A-Za-z0-9_][A-Za-z0-9_.-]*)?$')]
    [string]$Nas,

    [ValidatePattern('^/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$')]
    [string]$ProjectPath = '/volume1/docker/scoutanalyzer',

    [switch]$UseSudo,

    [switch]$PromptForSudo,

    [switch]$ResetKeepUsers
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$tempDir = Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString())
$remoteDir = $null
$sshOptions = @('-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10')

function Send-DeployFile {
    param([string]$LocalPath, [string]$RemotePath)

    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = (Get-Command ssh.exe -CommandType Application).Source
    $start.Arguments = "-T $($sshOptions -join ' ') $Nas `"umask 077; cat > '$RemotePath'`""
    $start.UseShellExecute = $false
    $start.RedirectStandardInput = $true
    $start.CreateNoWindow = $true
    $stream = [IO.File]::OpenRead($LocalPath)
    try {
        $process = [Diagnostics.Process]::Start($start)
        try {
            $inputStream = $process.StandardInput.BaseStream
            try { $stream.CopyTo($inputStream) } finally { $inputStream.Close() }
            $process.WaitForExit()
            if ($process.ExitCode -ne 0) {
                throw "Trasferimento SSH non riuscito per $([IO.Path]::GetFileName($LocalPath))."
            }
        } finally {
            $process.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
}

$remoteScript = @'
#!/bin/sh
set -eu
PATH="/usr/local/bin:/usr/bin:/bin:$PATH"
export PATH
project=$1
stage=$2
use_sudo=$3
case "$stage" in /tmp/scout-deploy.*) ;; *) exit 1 ;; esac

docker_cmd() {
    if [ "$use_sudo" = 0 ]; then docker "$@"; else sudo -n docker "$@"; fi
}

lock="$project/.backup-scoutanalyzer.lock"
locked=0
cleanup() {
    if [ "$locked" = 1 ]; then rmdir "$lock"; fi
    rm -rf -- "$stage"
}
trap cleanup 0
trap 'exit 1' HUP INT TERM

if [ "$use_sudo" = 2 ]; then sudo -v; fi

cd "$project"
test -f docker-compose.yml && test -f .env || {
    printf '%s\n' 'Progetto Compose o file .env assente sul NAS.' >&2
    exit 1
}
mkdir "$lock" || {
    printf '%s\n' 'Deploy o backup già in corso, oppure blocco residuo.' >&2
    exit 1
}
locked=1

mkdir "$stage/source"
tar -xzf "$stage/source.tar.gz" -C "$stage/source"
printf 'services:\n  scoutanalyzer:\n    build:\n      context: %s/source\n' "$stage" > "$stage/build.yml"

project_name=$(docker_cmd inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' scoutanalyzer)
case "$project_name" in ''|*[!a-z0-9_-]*)
    printf '%s\n' 'Impossibile identificare il progetto Compose del container scoutanalyzer.' >&2
    exit 1 ;;
esac

compose() {
    docker_cmd compose -p "$project_name" -f docker-compose.yml -f "$stage/build.yml" "$@"
}

# Check the mounts that the new container will use. The running container can
# still have old mounts from a previous version of the Compose file.
effective_compose=$(compose config)
if printf '%s\n' "$effective_compose" | grep -Eq '^[[:space:]]*target:[[:space:]]+/app(/(src|static|database|scripts)(/[^[:space:]]*)?|/web_app\.py)?/?[[:space:]]*$'; then
    printf '%s\n' 'Il Compose sul NAS monta ancora i sorgenti. Aggiorna docker-compose.yml prima del deploy.' >&2
    exit 1
fi
unset effective_compose

printf '%s\n' 'Compilazione della nuova immagine…'
compose build scoutanalyzer
printf '%s\n' 'Aggiornamento del container…'
compose up -d --no-build --no-deps scoutanalyzer

attempt=0
while [ "$attempt" -lt 30 ]; do
    if docker_cmd exec scoutanalyzer python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/api/version', timeout=3).close()" >/dev/null 2>&1; then
        printf '%s\n' 'ScoutAnalyzer risponde alla verifica di avvio.'
        exit 0
    fi
    attempt=$((attempt + 1))
    sleep 2
done
printf '%s\n' 'Il container non risponde. Controlla i log in Container Manager.' >&2
exit 1
'@

try {
    New-Item -ItemType Directory -Path $tempDir | Out-Null
    $stageOutput = ssh @sshOptions $Nas 'umask 077; mktemp -d /tmp/scout-deploy.XXXXXXXX'
    if ($LASTEXITCODE -ne 0 -or $stageOutput -cnotmatch '^/tmp/scout-deploy\.[a-zA-Z0-9]+$' -or @($stageOutput).Count -ne 1) {
        throw 'Impossibile preparare il NAS via SSH. Verifica account, chiave e host.'
    }
    $remoteDir = $stageOutput
    if ($ResetKeepUsers) {
        $scriptFile = Join-Path $tempDir 'reset.sh'
        $resetScript = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'reset_synology.sh')
        [IO.File]::WriteAllText($scriptFile, $resetScript.Replace("`r`n", "`n"))
        Send-DeployFile -LocalPath $scriptFile -RemotePath "$remoteDir/reset.sh"
        ssh @sshOptions -t $Nas "sudo sh '$remoteDir/reset.sh' '$ProjectPath'"
        if ($LASTEXITCODE -ne 0) { throw "Reset non riuscito sul NAS $Nas." }
        return
    }
    $archive = Join-Path $tempDir 'source.tar.gz'
    $fileList = Join-Path $tempDir 'files.txt'
    $scriptFile = Join-Path $tempDir 'deploy.sh'
    $runtimePaths = @(
        'Dockerfile', 'requirements.txt', 'web_app.py',
        ':(glob)src/**/*.py', ':(glob)database/**/*.py', 'database/schema.sql',
        'static', 'scripts/migrate_sqlite_to_postgres.py'
    )
    # Read the current working files, including changes that have not been committed.
    $files = @(git -C $repo -c core.quotePath=false ls-files --cached --others --exclude-standard -- $runtimePaths)
    if ($LASTEXITCODE -ne 0) { throw 'Lettura dei file del progetto non riuscita.' }
    $files = @($files | Sort-Object -Unique | Where-Object {
        ($_ -notlike 'static/*' -or $_ -match '\.(html|css|js|mjs|svg|png|jpe?g|webp|gif|ico|woff2?)$') -and
            (Test-Path -LiteralPath (Join-Path $repo $_) -PathType Leaf)
    })
    foreach ($required in @('Dockerfile', 'requirements.txt', 'web_app.py', 'database/schema.sql', 'static/index.html')) {
        if ($required -notin $files) { throw "File necessario mancante: $required" }
    }
    [IO.File]::WriteAllLines($fileList, [string[]]$files)
    tar -czf $archive -C $repo -T $fileList
    if ($LASTEXITCODE -ne 0) { throw 'Creazione del pacchetto non riuscita.' }
    [IO.File]::WriteAllText($scriptFile, $remoteScript.Replace("`r`n", "`n") + "`n")

    Send-DeployFile -LocalPath $archive -RemotePath "$remoteDir/source.tar.gz"
    Send-DeployFile -LocalPath $scriptFile -RemotePath "$remoteDir/deploy.sh"

    $sudoFlag = [int]$UseSudo.IsPresent
    $deployOptions = $sshOptions
    if ($PromptForSudo) {
        $sudoFlag = 2
        $deployOptions = $sshOptions + '-t'
    }
    ssh @deployOptions $Nas "sh '$remoteDir/deploy.sh' '$ProjectPath' '$remoteDir' '$sudoFlag'"
    if ($LASTEXITCODE -ne 0) { throw "Deploy non riuscito sul NAS $Nas." }
} finally {
    if ($remoteDir) {
        # The remote script removes the build directory. This covers interrupted transfers.
        ssh @sshOptions $Nas "if [ -d '$remoteDir' ]; then rm -f '$remoteDir/source.tar.gz' '$remoteDir/deploy.sh' '$remoteDir/reset.sh'; rmdir '$remoteDir'; fi"
    }
    foreach ($temporaryFile in @($archive, $fileList, $scriptFile)) {
        if ($temporaryFile -and (Test-Path -LiteralPath $temporaryFile)) {
            Remove-Item -LiteralPath $temporaryFile -Force
        }
    }
    if (Test-Path -LiteralPath $tempDir) { Remove-Item -LiteralPath $tempDir }
}
