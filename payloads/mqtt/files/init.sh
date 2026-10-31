#!/bin/sh
# Own only this bridge. Vendor services and SSH have separate lifecycles.
case "$1" in
    start)
        /usr/bin/python -B /usr/sbin/c100x-mqtt.py start </dev/null >/dev/null 2>&1 &
        ;;
    stop|status)
        /usr/bin/python -B /usr/sbin/c100x-mqtt.py "$1"
        ;;
    restart)
        "$0" stop && "$0" start
        ;;
    *) exit 2 ;;
esac
