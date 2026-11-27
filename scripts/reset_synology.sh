#!/bin/sh
# Run as an administrator on the NAS. The backup includes the original SQLite database and storage.
set -eu
umask 077
PATH="/usr/local/bin:/usr/bin:/bin:$PATH"
export PATH

project=$(cd "$1" && pwd -P)
case "$project" in /volume[0-9]*/*) ;; *) exit 1 ;; esac
cd "$project"
if ! { test -f docker-compose.yml && test -f .env && test -s data/scoutanalyzer.db && test -d storage && test -d config; }; then
    printf '%s\n' 'Progetto, database o cartelle del NAS mancanti.' >&2
    exit 1
fi

project_name=$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' scoutanalyzer)
case "$project_name" in ''|*[!a-z0-9_-]*) exit 1 ;; esac
compose() { docker compose -p "$project_name" -f docker-compose.yml "$@"; }
data_mount=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Source}}{{end}}{{end}}' scoutanalyzer)
storage_mount=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/app/storage"}}{{.Source}}{{end}}{{end}}' scoutanalyzer)
if [ "$data_mount" != "$project/data" ] || [ "$storage_mount" != "$project/storage" ]; then
    printf '%s\n' 'I mount del container non corrispondono alla cartella del progetto.' >&2
    exit 1
fi

move_contents() {
    for entry in "$1"/* "$1"/.[!.]* "$1"/..?*; do
        if [ -e "$entry" ] || [ -L "$entry" ]; then mv -- "$entry" "$2/" || return 1; fi
    done
}
database=data/scoutanalyzer.db
lock="$project/.backup-scoutanalyzer.lock"
mkdir "$lock" || { printf '%s\n' 'Backup, reset o deploy già in corso.' >&2; exit 1; }

restart=0
scratch=
storage_moved=0
committed=0
cleanup() {
    status=$?
    trap - 0
    trap '' HUP INT TERM
    if [ "$storage_moved" = 1 ] && [ "$committed" = 0 ]; then
        if ! move_contents "$scratch/storage" "$project/storage"; then
            printf 'Ripristino dei file incompleto. File residui in %s\n' "$scratch/storage" >&2
            scratch=
            restart=0
            status=1
        fi
    fi
    if [ "$restart" = 1 ]; then compose start scoutanalyzer || status=1; fi
    if [ -n "$scratch" ]; then rm -rf -- "$scratch" || status=1; fi
    rmdir "$lock" || status=1
    exit "$status"
}
trap cleanup 0
trap 'exit 1' HUP INT TERM

if [ "$(docker inspect --format '{{.State.Running}}' scoutanalyzer)" = true ]; then
    restart=1
    compose stop scoutanalyzer
fi

backup=$(mktemp -d "$(dirname "$project")/scoutanalyzer-pre-reset.XXXXXXXX")
tar -czf "$backup/backup.tar.gz" data storage config
tar -tzf "$backup/backup.tar.gz" >/dev/null
printf 'Backup verificato: %s/backup.tar.gz\n' "$backup"

scratch=$(mktemp -d "$project/.scout-reset.XXXXXXXX")
mkdir "$scratch/storage"
storage_moved=1
move_contents storage "$scratch/storage"

sqlite3 -bail "$database" <<'SQL'
PRAGMA foreign_keys = ON;
BEGIN IMMEDIATE;
DELETE FROM validation_logs;
DELETE FROM events;
DELETE FROM actions;
DELETE FROM rotations;
DELETE FROM match_sets;
DELETE FROM matches;
DELETE FROM team_players;
DELETE FROM user_teams;
DELETE FROM user_logins;
DELETE FROM players;
DELETE FROM teams;
DELETE FROM groups;
DELETE FROM championships;
DELETE FROM sqlite_sequence WHERE name NOT IN ('users', 'roles');
COMMIT;
SQL
committed=1
printf '%s\n' 'Dati e file azzerati. Account e password conservati.'
