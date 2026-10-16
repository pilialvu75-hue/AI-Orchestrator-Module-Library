import unittest
from tools.chat_supervision_snapshot import snapshot

class ChatSnapshotTests(unittest.TestCase):
    def test_unknown_lane_rejected(self):
        with self.assertRaises((FileNotFoundError, ValueError)):
            snapshot(".", "nonexistent-chat-lane")

if __name__ == "__main__":
    unittest.main()
