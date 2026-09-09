import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class Phase3FinalContentTests(unittest.TestCase):
 def test_canonical_source_is_complete_and_v2_corrected(self):
  rows=json.loads((ROOT/'data/phase3/learner-content-499-authored.json').read_text())['items'];by={x['stable_lexeme_key']:x for x in rows}
  self.assertEqual(len(rows),499);self.assertEqual(len(by),499)
  self.assertEqual(by['langue|NOM']['sense_id'],'__ws_4_langue__nom__1')
  self.assertEqual(by['appeler|VER']['sense_id'],'__ws_22_appeler__verb__1')
  self.assertEqual(by['engager|VER']['sense_id'],'__ws_6_engager__verb__1')
  self.assertTrue(all(x['content_status']=='external_semantic_authored' and x['cohort']=='phase3' for x in rows))
