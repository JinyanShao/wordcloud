import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_learner_sense_runtime import build
class LearnerSenseRuntimeTests(unittest.TestCase):
 def test_only_reviewed_phase2c_records_enter_runtime(self):
  payload=build(); rows=payload['records']
  self.assertEqual(len(rows),99)
  self.assertTrue(all(x['content_status']=='reviewed' for x in rows))
  self.assertFalse(any(x['stable_lexeme_key']=='travers|NOM' for x in rows))
 def test_exact_regression_senses_are_projected(self):
  by={x['stable_lexeme_key']:x for x in build()['records']}
  self.assertEqual(by['antenne|NOM']['sense_id'],'__ws_6_antenne__nom__1')
  self.assertEqual(by['maison|NOM']['gloss_zh_short'],'房子；住宅')
  self.assertEqual(by['temps|NOM']['example_fr'],'Le temps passe vite.')
if __name__=='__main__': unittest.main()
