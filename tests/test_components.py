import errno
import threading
import unittest
import urllib.request
from unittest.mock import MagicMock, patch

import microweb as web


class ComponentTests(unittest.TestCase):
    def component(self, name, events, fail_start=False, fail_stop=False):
        def start():
            events.append('start ' + name)
            if fail_start:
                raise ValueError('partial start ' + name)
        def stop():
            events.append('stop ' + name)
            if fail_stop:
                raise ValueError('stop failed ' + name)
        return web.Component(name, name.title(), web.App(), start, stop)

    def test_quiet_registration_and_start_stop_order(self):
        events, done = [], threading.Event()
        shell = web.Shell()
        shell.add(self.component('a', events), '/a')
        shell.add(self.component('b', events), '/b')
        self.assertEqual(events, [])
        def ready():
            events.append('ready')
            done.set()
        shell.run('127.0.0.1', 0, ready, stop_event=done)
        self.assertEqual(events, ['start a', 'start b', 'ready', 'stop b', 'stop a'])

    def test_bind_failure_starts_nothing(self):
        events = []
        component = self.component('a', events)
        with patch.object(web, '_Server', side_effect=OSError(errno.EADDRINUSE, 'occupied')):
            with self.assertRaises(SystemExit):
                component.run('127.0.0.1', 1)
        self.assertEqual(events, [])
        self.assertFalse(component._attempted)

    def test_partial_start_failure_cleans_failed_and_earlier_only(self):
        events = []
        shell = web.Shell()
        for name in ['a', 'b', 'c']:
            shell.add(self.component(name, events, fail_start=name == 'b'), '/' + name)
        ready = MagicMock()
        with self.assertRaisesRegex(ValueError, 'partial start b'):
            shell.run('127.0.0.1', 0, ready)
        ready.assert_not_called()
        self.assertEqual(events, ['start a', 'start b', 'stop b', 'stop a'])

    def test_stop_failure_does_not_block_other_cleanup(self):
        events, done = [], threading.Event()
        shell = web.Shell()
        shell.add(self.component('a', events), '/a')
        shell.add(self.component('b', events, fail_stop=True), '/b')
        with self.assertLogs('microweb', level='ERROR'), self.assertRaisesRegex(RuntimeError, 'cleanup'):
            shell.run('127.0.0.1', 0, done.set, stop_event=done)
        self.assertEqual(events[-2:], ['stop b', 'stop a'])

    def test_original_error_preserved_when_cleanup_fails(self):
        events = []
        component = self.component('a', events, fail_start=True, fail_stop=True)
        with self.assertLogs('microweb', level='ERROR'), self.assertRaisesRegex(ValueError, 'partial start'):
            component.run('127.0.0.1', 0)

    def test_server_cleanup_failure_still_closes_and_stops(self):
        events, done = [], threading.Event()
        server = MagicMock()
        server.socket.close.side_effect = OSError('socket close failed')
        component = self.component('a', events)
        with patch.object(web, '_Server', return_value=server):
            with self.assertRaisesRegex(OSError, 'socket close failed'):
                component.run('127.0.0.1', 0, done.set, stop_event=done)
        self.assertEqual(events, ['start a', 'stop a'])
        server.server_close.assert_called_once()

    def test_ready_exception_and_keyboard_interrupt_cleanup(self):
        for error in [ValueError('ready failed'), KeyboardInterrupt()]:
            events = []
            component = self.component('a', events)
            def ready():
                raise error
            if isinstance(error, KeyboardInterrupt):
                component.run('127.0.0.1', 0, ready)
            else:
                with self.assertRaisesRegex(ValueError, 'ready failed'):
                    component.run('127.0.0.1', 0, ready)
            self.assertEqual(events, ['start a', 'stop a'])

    def test_duplicates_plain_mount_and_single_run(self):
        events = []
        shell = web.Shell()
        first = self.component('a', events)
        shell.add(first, '/a')
        with self.assertRaises(ValueError):
            shell.add(self.component('a', events), '/another')
        with self.assertRaises(ValueError):
            shell.add(self.component('b', events), '/a')
        shell.mount('/plain', web.App())
        done = threading.Event()
        shell.run('127.0.0.1', 0, done.set, stop_event=done)
        first.stop()  # idempotent
        with self.assertRaises(RuntimeError):
            first.run('127.0.0.1', 0)
        self.assertEqual(events, ['start a', 'stop a'])

    def test_plain_app_and_empty_shell_lifecycle_optional(self):
        for app in [web.App(), web.Shell()]:
            done = threading.Event()
            app.run('127.0.0.1', 0, done.set, stop_event=done)

    def test_active_request_finishes_before_component_stop(self):
        entered, release, ready, done = [threading.Event() for _ in range(4)]
        events, servers, errors = [], [], []
        app = web.App()
        @app.get('/wait')
        def wait(req):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('test request was not released')
            events.append('handler done')
            return {'ok': True}
        component = web.Component('wait', 'Wait', app, stop=lambda: events.append('stop'))
        original = web._Server
        def capture(*args, **kwargs):
            server = original(*args, **kwargs)
            servers.append(server)
            return server
        def host():
            try:
                component.run('127.0.0.1', 0, ready.set, stop_event=done)
            except BaseException as error:
                errors.append(error)
        def request(url):
            try:
                with urllib.request.urlopen(url, timeout=8) as response:
                    response.read()
            except BaseException as error:
                errors.append(error)
        with patch.object(web, '_Server', side_effect=capture):
            thread = threading.Thread(target=host)
            thread.start()
            try:
                self.assertTrue(ready.wait(5))
                client = threading.Thread(target=request, args=(f'http://127.0.0.1:{servers[0].server_port}/wait',))
                client.start()
                self.assertTrue(entered.wait(5))
                done.set()
                self.assertNotIn('stop', events)
                release.set()
                client.join(8)
            finally:
                release.set()
                done.set()
                thread.join(8)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(events, ['handler done', 'stop'])


if __name__ == '__main__':
    unittest.main()
