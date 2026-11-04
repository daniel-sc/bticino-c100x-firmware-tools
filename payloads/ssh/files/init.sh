#!/bin/sh
# Own SSH independently of the vendor's persistent abil_ssh policy.
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
DAEMON="/usr/sbin/dropbear"
PIDFILE="/var/run/c100x-ssh.pid"
HOST_KEY="/etc/dropbear/classe100x_ecdsa_host_key"

running() {
    start-stop-daemon -K -t -q -p "$PIDFILE" -x "$DAEMON"
}

start() {
    if running; then
        return 0
    fi
    if [ ! -x "$DAEMON" ] || [ ! -s "$HOST_KEY" ] || [ ! -r "/etc/default/c100x-ssh" ]; then
        echo "c100x-ssh: missing daemon, host key or configuration" >&2
        return 1
    fi
    PASSWORD_AUTH=
    . "/etc/default/c100x-ssh"
    set -- -r "$HOST_KEY" -p 22 -P "$PIDFILE"
    case "$PASSWORD_AUTH" in
        0) set -- "$@" -s ;;
        1) ;;
        *) echo "c100x-ssh: invalid PASSWORD_AUTH" >&2; return 1 ;;
    esac
    start-stop-daemon -S -p "$PIDFILE" -x "$DAEMON" -- "$@" || return 1
    # Dropbear forks itself and writes its own PID file. Wait for that process,
    # rather than treating launcher completion as proof that it stayed running.
    attempts=0
    while ! running; do
        attempts=$((attempts + 1))
        if [ "$attempts" -ge 5 ]; then
            echo "c100x-ssh: daemon did not stay running; check syslog" >&2
            return 1
        fi
        sleep 1
    done
}

stop() {
    if running; then
        start-stop-daemon -K -p "$PIDFILE" -x "$DAEMON" || return 1
        attempts=0
        while running; do
            attempts=$((attempts + 1))
            if [ "$attempts" -ge 5 ]; then
                echo "c100x-ssh: daemon did not stop" >&2
                return 1
            fi
            sleep 1
        done
    fi
    rm -f "$PIDFILE"
}

case "$1" in
    start) start ;;
    stop) stop ;;
    restart|force-reload) stop && start ;;
    status)
        if running; then
            echo "c100x-ssh: running"
        else
            echo "c100x-ssh: stopped"
            exit 3
        fi
        ;;
    *) echo "Usage: $0 {start|stop|restart|force-reload|status}" >&2; exit 2 ;;
esac
