import unittest
from unittest.mock import patch
from pikabot.config import load
from pikabot.thermal import ThermalState
from pikabot.actions import ActionManager, candidates
from pikabot.monitor import ProcessInfo, Monitor

class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.config = load()
        self.browser = ProcessInfo(987654, 'chrome.exe', 40, 1200, 'chrome.exe', ())

    def test_hysteresis(self):
        state = ThermalState(self.config)
        self.assertEqual([state.update(t).name for t in [65,75,85,95,89,84,74,64]],
                         ['SAFE','WARM','HOT','CRITICAL','CRITICAL','HOT','WARM','SAFE'])

    def test_protection(self):
        for name in self.config['protected'] + self.config['whitelist']:
            proc = ProcessInfo(987654, name, 100, 2000, name, ())
            self.assertEqual(candidates((proc,), self.config), [])

    def test_simulation_never_opens_process(self):
        self.config['dry_run'] = False
        manager = ActionManager(self.config, True)
        choice = candidates((self.browser,), self.config)[0]
        with patch('pikabot.actions.psutil.Process') as process:
            self.assertEqual(manager.close(choice, 95, True), 'dry run')
            process.assert_not_called()
        self.assertEqual(manager.close(choice, 95, True), 'cooldown')

    def test_declined_close(self):
        choice = candidates((self.browser,), self.config)[0]
        with patch('pikabot.actions.psutil.Process') as process:
            self.assertEqual(ActionManager(self.config).close(choice, 95, False), 'cancelled')
            process.assert_not_called()

    def test_sensor_unavailable(self):
        with patch('pikabot.monitor.urlopen', side_effect=OSError):
            with patch('pikabot.monitor.psutil.sensors_temperatures', return_value={}, create=True):
                self.assertIsNone(Monitor(self.config).sensors()[0])

    def test_critical_dry_run_cannot_change_power(self):
        from pikabot.main import App
        from pikabot.thermal import Level
        from types import SimpleNamespace
        app = App.__new__(App)
        app.config = self.config
        app.config.update(dry_run=True, allow_critical_hibernate=True)
        app.hot_since = None
        app.power_saver_set = False
        with patch('pikabot.main.subprocess.run') as run:
            app._critical_response(SimpleNamespace(temperature_c=95), Level.CRITICAL)
            run.assert_not_called()

    def test_hibernate_requires_sustained_rise(self):
        from pikabot.main import App
        from pikabot.thermal import Level
        from types import SimpleNamespace
        app = App.__new__(App)
        app.config = self.config
        app.config.update(dry_run=False, auto_actions_paused=False, allow_critical_hibernate=True)
        app.hot_since = 100
        app.hot_start_temp = 92
        app.power_saver_set = True
        with patch('pikabot.main.time.monotonic', return_value=161), patch('pikabot.main.subprocess.run') as run:
            app._critical_response(SimpleNamespace(temperature_c=91), Level.CRITICAL)
            run.assert_not_called()
            app._critical_response(SimpleNamespace(temperature_c=95), Level.CRITICAL)
            self.assertEqual(run.call_args.args[0], ['shutdown', '/h'])

if __name__ == '__main__':
    unittest.main()
