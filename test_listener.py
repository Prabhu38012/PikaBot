import unittest
from pikabot.listener import WakeSession

class WakeTests(unittest.TestCase):
    def test_full_temperature_question(self):
        session = WakeSession()
        session.accept('hey pikabot', 0.9, 1)
        self.assertEqual(session.accept('What is the temperature of my laptop?', 0.50, 2), 'temperature')
        self.assertEqual(session.accept('cool down', 0.5, 2), 'unknown')
        self.assertEqual(session.accept('Please delete my files', 0.9, 3), 'unknown')
        self.assertTrue(session.active)
    def test_requires_wake(self):
        session = WakeSession()
        self.assertIsNone(session.accept('cool down', 0.9, 100))
        self.assertEqual(session.accept('hey pika bot', 0.9, 100), 'wake')
        self.assertEqual(session.accept('temperature', 0.9, 105), 'temperature')
        self.assertEqual(session.accept('cool down', 0.9, 106), 'cool down')

    def test_persists_and_ends_on_break(self):
        session = WakeSession()
        self.assertIsNone(session.accept('hey pikabot', 0.2, 100))
        session.accept('hey pikabot', 0.9, 100)
        self.assertEqual(session.accept('temperature', 0.9, 3600), 'temperature')
        self.assertEqual(session.accept('Okay, you may take a break.', 0.9, 3601), 'break')
        self.assertIsNone(session.accept('cool down', 0.9, 3602))
        self.assertEqual(session.accept('hey pikabot', 0.9, 3603), 'wake')
        self.assertEqual(session.accept('status', 0.9, 3604), 'status')

    def test_thank_you_does_not_sleep(self):
        session = WakeSession()
        session.accept('hey pikabot', 0.9, 1)
        self.assertEqual(session.accept('thank you', 0.9, 2), 'thank you')
        self.assertTrue(session.active)

    def test_break_with_misheard_intro(self):
        session = WakeSession()
        session.accept('hey pikabot', 0.9, 1)
        self.assertEqual(session.accept('Bouquet you may take a break', 0.79, 2), 'break')

if __name__ == '__main__':
    unittest.main()
