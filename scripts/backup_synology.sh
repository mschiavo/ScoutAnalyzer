#!/bin/sh
# Uso: sh backup_synology.sh CARTELLA_PROGETTO CARTELLA_BACKUP
set -eu
umask 077
PATH="/usr/local/bin:/usr/bin:/bin:$PATH"
export PATH LC_ALL=C

die() {
    printf '%s\n' "$*" >&2
    exit 1
}

[ "$#" -eq 2 ] || die "Uso: $0 CARTELLA_PROGETTO CARTELLA_BACKUP"
project=$(cd "$1" && pwd -P)
destination=$(cd "$2" && pwd -P)
case "$destination/" in
    "$project/"*) die "Scegli una destinazione esterna alla cartella del progetto." ;;
esac
cd "$project"
[ -f docker-compose.yml ] || die "docker-compose.yml assente in $project"
[ -s data/scoutanalyzer.db ] || die "Database SQLite assente o vuoto."
[ -d storage ] && [ -d config ] || die "Cartella storage o config assente."

compose() {
    docker compose -f docker-compose.yml "$@"
}

lock="$project/.backup-scoutanalyzer.lock"
mkdir "$lock" || die "Backup già in corso o blocco residuo: $lock"
restart=0
temporary=
cleanup() {
    status=$?
    trap - 0
    trap '' HUP INT TERM
    if [ "$restart" -eq 1 ] && ! compose start scoutanalyzer; then
        printf '%s\n' "Riavvio fallito: avvia ScoutAnalyzer in Container Manager." >&2
        status=1
    fi
    if [ -n "$temporary" ]; then
        rm -f "$temporary" || status=1
    fi
    rmdir "$lock" || status=1
    exit "$status"
}
trap cleanup 0
trap 'exit 1' HUP INT TERM

stamp=$(date '+%Y%m%d-%H%M%S')
archive="$destination/scoutanalyzer-$stamp.tar.gz"
[ ! -e "$archive" ] || die "Archivio già presente: $archive"
temporary=$(mktemp "$destination/.scoutanalyzer-$stamp.XXXXXX")

container=$(compose ps -q scoutanalyzer)
if [ -n "$container" ]; then
    running=$(docker inspect --format '{{.State.Running}}' "$container")
    if [ "$running" = true ]; then
        restart=1
        compose stop scoutanalyzer
    fi
fi

tar -czf "$temporary" data storage config

if [ "$restart" -eq 1 ]; then
    compose start scoutanalyzer
    restart=0
fi

tar -tzf "$temporary" >/dev/null
mv "$temporary" "$archive"
temporary=
printf 'Backup completato: %s\n' "$archive"
