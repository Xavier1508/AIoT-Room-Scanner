import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DATA_HEADER = ROOT / "src" / "ml_model_data.h"
META_HEADER = ROOT / "src" / "ml_model_metadata.h"
MODEL = ROOT / "research" / "mapping" / "ml" / "model-empty-human-v2" / "model.tflite"


class MlAssets(unittest.TestCase):
    def test_header_matches_trained_tflite(self):
        text = DATA_HEADER.read_text(encoding="utf-8")
        start = text.index("{") + 1
        end = text.index("};")
        raw = bytes(int(value.strip()) for value in text[start:end].replace("\n", " ").split(",")
                    if value.strip())
        self.assertEqual(len(raw), int(re.search(r"g_model_len = (\d+)", text).group(1)))
        if MODEL.is_file():
            self.assertEqual(raw, MODEL.read_bytes())
        self.assertLess(len(raw), 50 * 1024)

    def test_metadata_contract(self):
        text = META_HEADER.read_text(encoding="utf-8")
        self.assertIn("#define ML_WINDOW 32", text)
        self.assertIn("#define ML_FEATURES 6", text)
        self.assertIn("#define ML_CLASSES 2", text)
        self.assertIn('"empty"', text)
        self.assertIn('"human"', text)
        mean = re.search(r"ML_MEAN\[\] = \{([^}]*)\}", text).group(1)
        std = re.search(r"ML_STD\[\] = \{([^}]*)\}", text).group(1)
        self.assertEqual(len([v for v in mean.split(",") if v.strip()]), 6)
        self.assertEqual(len([v for v in std.split(",") if v.strip()]), 6)


if __name__ == "__main__":
    unittest.main()
