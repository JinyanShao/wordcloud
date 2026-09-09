import json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import build_phase3_remaining_content_inputs as remaining
class Phase3RemainingContentInputsTests(unittest.TestCase):
 def setUp(self):self.rows=json.loads(remaining.OUT.read_text())['items']
 def test_exact_partition(self):
  old={x['stable_lexeme_key'] for x in json.loads(remaining.EXISTING.read_text())['items']};new={x['stable_lexeme_key'] for x in self.rows}
  self.assertEqual(len(new),349);self.assertFalse(old&new);self.assertNotIn('cesse|NOM',new)
 def test_packets_are_prose_free_and_exact(self):
  manifest=json.loads((remaining.PACKETS/'manifest.json').read_text());rows=[]
  for entry in manifest['packets']:rows.extend(json.loads(line) for line in (remaining.PACKETS/entry['filename']).read_text().splitlines())
  self.assertEqual([x['key'] for x in rows],[x['stable_lexeme_key'] for x in self.rows])
  self.assertTrue(all(not {'gloss_zh_short','example_fr','example_zh'}&set(x) for x in rows))
