import json
import io
from contextlib import redirect_stderr
from pathlib import Path
import tempfile
import signal
import subprocess
import sys
import textwrap
import unittest
from unittest.mock import patch

import classe100x
from classe100x.linux_usb import Interface, Network, discover, linux_usb_session
from classe100x.usb_session import USBError, usb_session
from classe100x.diagnostics import tool_error


class LinuxUSBTests(unittest.TestCase):
    def test_discovery_uses_usb_ancestry_and_rejects_multiple_devices(self):
        with tempfile.TemporaryDirectory() as directory:
            # Exercise aliased paths on every host, as with macOS /var -> /private/var.
            real = Path(directory) / 'real-sysfs'
            real.mkdir()
            root = Path(directory) / 'sysfs'
            root.symlink_to(real, target_is_directory=True)
            usb = root / 'bus/usb/devices/1-2'
            usb.mkdir(parents=True)
            (usb / 'idVendor').write_text('1da4\n')
            (usb / 'idProduct').write_text('0056\n')
            (usb / 'devnum').write_text('3\n')
            net = usb / '1-2:1.0/net/enxfixture'
            net.mkdir(parents=True)
            (net / 'ifindex').write_text('42\n')
            interfaces = root / 'class/net'
            interfaces.mkdir(parents=True)
            (interfaces / 'enxfixture').symlink_to(net)
            (interfaces / 'eth0').mkdir()
            self.assertEqual(discover(root), Interface('enxfixture', net.resolve(), 42, '3'))
            (usb / 'devnum').write_text('4')
            self.assertEqual(discover(root).device_number, '4')
            other = usb.with_name('1-3')
            other.mkdir()
            (other / 'idVendor').write_text('1da4')
            (other / 'idProduct').write_text('0056')
            with self.assertRaisesRegex(USBError, 'only one'):
                discover(root)
            (other / 'idVendor').write_text('1234')
            (interfaces / 'enxfixture').unlink()
            self.assertIsNone(discover(root))

    def fixture(self):
        network = Network()
        interface = Interface('enxfixture', Path('/fixture/usb/net/enxfixture'), 42, '3')
        current = self.enterContext(patch('classe100x.linux_usb.discover', return_value=interface))
        state = {'active': 'old-profile', 'profiles': {'old-profile'}, 'routes': [],
                 'destination': {'dev': interface.name, 'prefsrc': '192.168.129.2'}, 'fail_up': False,
                 'nm_state': 'disconnected'}
        calls = []

        def run(*args):
            calls.append(args)
            if args[0] == network.ip:
                if 'link' in args:
                    return '[{"ifname":"enxfixture"}]'
                return json.dumps([state['destination']] if 'get' in args else state['routes'])
            command = args[3:]
            if command[-2:] == ('device', 'status'):
                return '' if state['nm_state'] == 'missing' else interface.name + ':' + state['nm_state']
            if command[:2] == ('-g', 'GENERAL.CON-UUID'):
                return state['active'] or '--'
            if command[:2] == ('-g', 'UUID'):
                return '\n'.join(state['profiles'])
            if command[:2] == ('connection', 'add'):
                self.assertEqual(command[2:4], ('save', 'no'))
                state['profiles'].add(command[command.index('connection.uuid') + 1])
            elif command[:2] == ('connection', 'up'):
                state['active'] = command[3]
                if state['fail_up']:
                    state['fail_up'] = False
                    raise USBError('activation timeout after applying profile')
            elif command[:2] == ('connection', 'delete'):
                state['profiles'].remove(command[3])
                if state['active'] == command[3]:
                    state['active'] = None
            else:
                self.fail(f'unexpected command: {command}')
            return ''

        self.enterContext(patch('classe100x.linux_usb.run', side_effect=run))
        return network, interface, current, state, calls

    def test_temporary_profile_restored_after_success_or_uncertain_activation(self):
        network, interface, current, state, calls = self.fixture()
        for fail in (False, True):
            state['fail_up'] = fail
            if fail:
                with self.assertRaisesRegex(USBError, 'activation timeout'):
                    network.check(timeout=0)
            else:
                network.check(timeout=0)
                network.check(timeout=0)
            network.close()
            self.assertEqual(state['profiles'], {'old-profile'})
            self.assertEqual(state['active'], 'old-profile')

    def test_reenumeration_does_not_restore_old_connection_on_new_interface(self):
        network, interface, current, state, calls = self.fixture()
        network.check(timeout=0)
        old_profile = network.profile
        replacement = Interface(interface.name, interface.path, 43, '4')
        current.return_value = replacement
        state['active'] = None
        network.check(timeout=0)
        self.assertNotEqual(network.profile, old_profile)
        self.assertNotIn(old_profile, state['profiles'])
        network.close()
        self.assertIsNone(state['active'])
        self.assertFalse(any(c[3:7] == ('connection', 'up', 'uuid', 'old-profile') for c in calls))

    def test_subnet_conflict_fails_before_network_changes(self):
        network, interface, current, state, calls = self.fixture()
        state['routes'] = [{'dst': '192.168.129.0/24', 'dev': 'vpn0'}]
        with self.assertRaisesRegex(USBError, 'conflicts'):
            network.check(timeout=0)
        self.assertEqual(state['profiles'], {'old-profile'})
        self.assertFalse(any('add' in call for call in calls))

    def test_wrong_route_source_and_lost_ownership_stop_without_reconfiguration(self):
        network, interface, current, state, calls = self.fixture()
        network.check(timeout=0)
        for route in ({'dev': 'eth0', 'prefsrc': '192.168.129.2'},
                      {'dev': interface.name, 'prefsrc': '192.168.1.2'}):
            state['destination'] = route
            with self.assertRaisesRegex(USBError, 'route/source'):
                network.check(timeout=0)
        state['active'] = 'user-changed-profile'
        with self.assertRaisesRegex(USBError, 'ownership changed'):
            network.check(timeout=0)
        network.close()
        self.assertEqual(state['active'], 'user-changed-profile')
        self.assertEqual(sum('add' in call for call in calls), 1)

    def test_linux_dispatch_does_not_require_tetherkit_and_checks_root(self):
        with patch('classe100x.usb_session.sys.platform', 'linux'), \
                patch('classe100x.linux_usb.os.geteuid', return_value=1000):
            with self.assertRaisesRegex(PermissionError, 'sudo'):
                with usb_session(Path('/missing/tetherkit')):
                    self.fail('root check bypassed')

    def test_cleanup_removes_owned_profile_even_when_interface_cannot_be_identified(self):
        for failure in ('ambiguous', 'disappeared'):
            with self.subTest(failure=failure):
                network, interface, current, state, calls = self.fixture()
                network.check(timeout=0)
                if failure == 'ambiguous':
                    current.side_effect = USBError('Connect only one C100X USB device')
                else:
                    self.enterContext(patch.object(network, 'active', side_effect=USBError('No device found')))
                with self.assertRaisesRegex(USBError, 'profile removed'):
                    network.close()
                self.assertEqual(state['profiles'], {'old-profile'})
                self.assertIsNone(state['active'])
                self.assertIsNone(network.profile)
                self.assertFalse(any(c[3:7] == ('connection', 'up', 'uuid', 'old-profile') for c in calls))

    def test_cleanup_warning_retains_tool_details_and_primary_error(self):
        import os
        network, interface, current, state, calls = self.fixture()
        error = tool_error(USBError('Linux USB network command failed'), 'nmcli', 10,
                           'fixture: profile deletion denied')
        output = io.StringIO()
        with tempfile.TemporaryFile() as lock, \
                patch('classe100x.linux_usb.os.geteuid', return_value=0), \
                patch('classe100x.linux_usb.os.open', return_value=os.dup(lock.fileno())), \
                patch('classe100x.linux_usb.Network', return_value=network), \
                patch.object(network, 'check'), \
                patch.object(network, 'close', side_effect=error), redirect_stderr(output):
            with self.assertRaisesRegex(RuntimeError, 'primary failure'):
                with linux_usb_session():
                    raise RuntimeError('primary failure')
        self.assertIn('fixture: profile deletion denied', output.getvalue())
        self.assertIn('exit status: 10', output.getvalue())

    def test_cancellation_finishes_cleanup_and_restores_signal_handlers(self):
        import os
        network, interface, current, state, calls = self.fixture()
        previous = signal.getsignal(signal.SIGTERM)
        with tempfile.TemporaryFile() as lock, \
                patch('classe100x.linux_usb.os.geteuid', return_value=0), \
                patch('classe100x.linux_usb.os.open', return_value=os.dup(lock.fileno())), \
                patch('classe100x.linux_usb.Network', return_value=network):
            with self.assertRaises(KeyboardInterrupt):
                with linux_usb_session():
                    signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        self.assertEqual(state['active'], 'old-profile')
        self.assertEqual(state['profiles'], {'old-profile'})
        self.assertIs(signal.getsignal(signal.SIGTERM), previous)

    def test_terminal_interrupt_during_profile_deletion_finishes_cleanup(self):
        # Isolate the terminal process group; only the disposable child runs for real.
        script = textwrap.dedent('''
            import os, signal, sys, tempfile
            from unittest.mock import patch
            sys.path[:0] = sys.argv[1:]
            from classe100x import linux_usb
            from test_linux_usb import LinuxUSBTests

            real_run = linux_usb.run
            case = LinuxUSBTests()
            network, interface, current, state, calls = case.fixture()
            fake_run = linux_usb.run

            def command(*args):
                if args[3:5] == ('connection', 'delete'):
                    real_run(sys.executable, '-c',
                             'import os, signal, sys; os.killpg(int(sys.argv[1]), signal.SIGINT)',
                             str(os.getpgrp()))
                return fake_run(*args)

            with tempfile.TemporaryFile() as lock, \\
                    patch.object(linux_usb.os, 'geteuid', return_value=0), \\
                    patch.object(linux_usb.os, 'open', return_value=os.dup(lock.fileno())), \\
                    patch.object(linux_usb, 'Network', return_value=network), \\
                    patch.object(linux_usb, 'run', side_effect=command):
                with case.assertRaises(KeyboardInterrupt):
                    with linux_usb.linux_usb_session():
                        pass
            case.assertEqual(state['profiles'], {'old-profile'})
            case.assertEqual(state['active'], 'old-profile')
        ''')
        result = subprocess.run([sys.executable, '-I', '-B', '-c', script,
                                 str(Path(__file__).resolve().parent),
                                 str(Path(classe100x.__file__).resolve().parent.parent)],
                                capture_output=True, text=True, start_new_session=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_hotplug_waits_for_networkmanager_but_unmanaged_times_out(self):
        network, interface, current, state, calls = self.fixture()
        state['nm_state'] = 'missing'
        states = iter(('unmanaged', 'disconnected'))
        with patch('classe100x.linux_usb.time.sleep',
                   side_effect=lambda _: state.update(nm_state=next(states))):
            network.check(timeout=45)
        self.assertEqual(state['active'], network.profile)
        self.assertEqual(sum('add' in call for call in calls), 1)
        network.close()
        state['nm_state'] = 'unmanaged'
        with self.assertRaisesRegex(USBError, 'NetworkManager'):
            network.check(timeout=0)
        self.assertEqual(state['profiles'], {'old-profile'})
