import math
import unittest
from pathlib import Path

from gf3_l1a2l2.metadata import read_calibration_metadata


class MetadataTests(unittest.TestCase):
    def test_reads_named_calibration_values(self):
        path = Path(__file__).parent / "fixtures" / "sample.meta.xml"
        metadata = read_calibration_metadata(path)

        self.assertEqual(metadata.for_polarization("HH").qualify_value, 1.0)
        self.assertEqual(metadata.for_polarization("HV").calibration_const, 20.0)
        self.assertTrue(math.isnan(metadata.for_polarization("VH").qualify_value))


if __name__ == "__main__":
    unittest.main()
