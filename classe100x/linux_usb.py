"""Experimental Ubuntu USB networking using native drivers and NetworkManager.

Only a temporary connection profile is owned here. Firmware sequencing stays in
the updater; neither driver installation nor persistent network edits belong here.
"""

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

from .diagnostics import format_failure, tool_error
from .resources import bundled_tool
from .usb_session import USBError


@dataclass(frozen=True)
class Interface:
    name: str
    path: Path
    index: int
    device_number: str


def discover(sysfs=Path('/sys')):
    """Match USB ancestry, not interface names, MACs or ordinary LAN routes."""
    devices = []
    for device in (sysfs / 'bus/usb/devices').glob('*'):
        try:
            if (device.joinpath('idVendor').read_text().strip() == '1da4'
                    and device.joinpath('idProduct').read_text().strip() == '0056'):
                devices.append(device.resolve())
        except FileNotFoundError:
            continue  # Includes a device disappearing during enumeration.
    if len(devices) > 1:
        raise USBError('Connect only one C100X USB device')
    if not devices:
        return None
    interfaces = []
    for entry in (sysfs / 'class/net').glob('*'):
        try:
            path = entry.resolve(strict=True)
            if path.is_relative_to(devices[0]):
                interfaces.append(Interface(entry.name, path, int((entry / 'ifindex').read_text()),
                                            (devices[0] / 'devnum').read_text().strip()))
        except FileNotFoundError:
            continue
    if len(interfaces) > 1:
        raise USBError('C100X native USB network interface is ambiguous')
    return next(iter(interfaces), None)


def run(*command):
    try:
        # Terminal signals belong to the session owner, which defers them during
        # cleanup. Ordinary cancellation still kills this child via subprocess.run.
        result = subprocess.run(list(map(str, command)), capture_output=True, text=True,
                                timeout=15, start_new_session=True, env={**os.environ, 'LC_ALL': 'C'})
    except FileNotFoundError as exc:
        raise USBError(f'Missing {command[0]}; use the release bundle on Ubuntu 24.04/26.04 Desktop '
                       'with its default NetworkManager installation') from exc
    except subprocess.TimeoutExpired as exc:
        raise USBError(f'Linux USB network command timed out: {command[0]}') from exc
    if result.returncode:
        raise tool_error(USBError('Linux USB network command failed'), str(command[0]),
                         result.returncode, result.stderr)
    return result.stdout.strip()


class Network:
    def __init__(self):
        bundled = bundled_tool('ip')
        self.ip = str(bundled if bundled.is_file() else Path('/usr/sbin/ip'))
        # Match the host NetworkManager service with its installed client.
        self.nmcli = '/usr/bin/nmcli'
        self.interface = None
        self.profile = None
        self.previous = None
        self.activating = False

    def nm(self, *args):
        return run(self.nmcli, '--wait', '10', *args)

    def active(self, interface):
        value = self.nm('-g', 'GENERAL.CON-UUID', 'device', 'show', interface.name)
        return None if value in ('', '--') else value

    def managed(self, interface):
        # Sysfs can lead NetworkManager during hotplug. Query the list so an
        # interface not yet known to NM is a readiness observation, not a tool error.
        rows = self.nm('-t', '--escape', 'no', '-f', 'DEVICE,STATE', 'device', 'status')
        states = dict(row.split(':', 1) for row in rows.splitlines())
        return states.get(interface.name) not in (None, 'unmanaged')

    def conflicts(self, interface):
        subnet = ipaddress.ip_network('192.168.129.0/30')
        for route in json.loads(run(self.ip, '-j', '-4', 'route', 'show', 'table', 'all')):
            destination = route.get('dst', 'default')
            if destination == 'default' or route.get('dev') == interface.name:
                continue
            if ipaddress.ip_network(destination, strict=False).overlaps(subnet):
                raise USBError('C100X USB subnet conflicts with an existing route; '
                               'disconnect the conflicting VPN/network before retrying preflight')

    def configure(self, interface):
        self.conflicts(interface)
        link = json.loads(run(self.ip, '-j', 'link', 'show', 'dev', interface.name))
        if len(link) != 1 or link[0].get('master'):
            raise USBError('C100X USB interface belongs to a bridge/bond or is unavailable')
        previous = self.active(interface)
        if discover() != interface:
            raise USBError('C100X USB interface changed before configuration')
        self.interface, self.previous = interface, previous
        # Record ownership before the call: a timeout may still create the profile.
        self.profile = str(uuid.uuid4())
        self.nm('connection', 'add', 'save', 'no', 'type', 'ethernet',
                'ifname', interface.name, 'con-name', 'c100x-usb-' + self.profile,
                'connection.uuid', self.profile, 'connection.autoconnect', 'no',
                'ipv4.method', 'manual', 'ipv4.addresses', '192.168.129.2/30',
                'ipv4.never-default', 'yes', 'ipv4.ignore-auto-dns', 'yes',
                'ipv6.method', 'disabled')
        if discover() != interface:
            raise USBError('C100X USB interface changed before activation')
        self.activating = True
        self.nm('connection', 'up', 'uuid', self.profile, 'ifname', interface.name)

    def verify(self, interface):
        if self.active(interface) != self.profile:
            raise USBError('C100X USB connection ownership changed; stop other network configuration')
        # Check both automatic source selection and source-specific policy routing.
        for source in ((), ('from', '192.168.129.2')):
            routes = json.loads(run(self.ip, '-j', '-4', 'route', 'get', '192.168.129.1', *source))
            if (len(routes) != 1 or routes[0].get('dev') != interface.name
                    or routes[0].get('prefsrc', routes[0].get('src', routes[0].get('from'))) != '192.168.129.2'
                    or routes[0].get('gateway')):
                raise USBError('Intercom route/source is not through the managed C100X USB interface; '
                               'check conflicting VPNs or policy routes')
        if discover() != interface:
            raise USBError('C100X USB interface changed during route verification')

    def check(self, timeout=10):
        deadline = time.monotonic() + timeout
        while True:
            interface = discover()
            if interface is not None and (interface == self.interface or self.managed(interface)):
                if interface != self.interface:
                    self.close()
                    self.configure(interface)
                    print(f'USB networking ready on {interface.name} (Linux native)', file=sys.stderr)
                self.verify(interface)
                return
            if time.monotonic() >= deadline:
                if interface is not None:
                    raise USBError('C100X USB interface is not ready in NetworkManager; '
                                   'use the default Ubuntu Desktop managed network setup')
                raise USBError('C100X USB networking is not ready; check cable/power and Ubuntu '
                               'native rndis_host/cdc_ether driver binding (no custom driver fallback)')
            time.sleep(0.2)

    def close(self):
        if self.profile is None:
            return
        interface, profile, previous = self.interface, self.profile, self.previous
        identity_error = None
        same, active = False, None
        try:
            same = discover() == interface
            active = self.active(interface) if same else None
        except (OSError, ValueError) as exc:
            # Losing discovery or the interface must not strand our known UUID.
            # It only prevents restoration, which needs proven identity/ownership.
            same = False
            identity_error = exc
        profiles = self.nm('-g', 'UUID', 'connection', 'show').splitlines()
        if profile in profiles:
            self.nm('connection', 'delete', 'uuid', profile)
        if (same and self.activating and previous and active in (None, profile)
                and discover() == interface and self.active(interface) in (None, previous)):
            self.nm('connection', 'up', 'uuid', previous, 'ifname', interface.name)
        # Retain ownership if a handover cleanup fails or is interrupted, so the
        # surrounding context still has enough information to finish teardown.
        self.interface = self.profile = self.previous = None
        self.activating = False
        if identity_error is not None:
            raise USBError('Temporary USB profile removed; prior connection restoration '
                           'could not be verified') from identity_error


@contextmanager
def linux_usb_session():
    if os.geteuid() != 0:
        raise PermissionError('USB networking needs root; run the device command with sudo')
    # Concurrent commands must not replace each other's temporary connection.
    fd = os.open('/run/lock/c100x-usb.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise USBError('Another C100X USB session is running') from exc
        network = Network()
        previous = {}

        def interrupt(signum, frame):
            for sig in previous:
                signal.signal(sig, signal.SIG_IGN)
            raise KeyboardInterrupt

        try:
            for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                previous[sig] = signal.signal(sig, interrupt)
            print('Experimental Linux USB: waiting for native networking…', file=sys.stderr)
            network.check(timeout=45)
            yield network.check
        finally:
            # Finish bounded host cleanup even if cancellation arrives during it.
            interrupted = False

            def defer(signum, frame):
                nonlocal interrupted
                interrupted = True

            for sig in previous:
                signal.signal(sig, defer)
            try:
                network.close()
            except (OSError, ValueError) as exc:
                print(f'USB network cleanup incomplete: {format_failure(exc)}. Inspect NetworkManager connections '
                      'named c100x-usb-* before another session.', file=sys.stderr)
            finally:
                for sig, handler in previous.items():
                    signal.signal(sig, handler)
            if interrupted:
                raise KeyboardInterrupt
