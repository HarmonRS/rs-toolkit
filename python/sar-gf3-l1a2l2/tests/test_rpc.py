import unittest
from pathlib import Path

from gf3_l1a2l2.rpc import read_rpc_metadata


class RpcTests(unittest.TestCase):
    def test_reads_rpc_metadata(self):
        path = Path(__file__).parent / "fixtures" / "sample.rpb"
        metadata = read_rpc_metadata(path)

        self.assertEqual(metadata["ERR_BIAS"], "-1")
        self.assertEqual(metadata["LINE_OFF"], "10")
        self.assertEqual(metadata["LINE_NUM_COEFF"], "1 2 3")


if __name__ == "__main__":
    unittest.main()
