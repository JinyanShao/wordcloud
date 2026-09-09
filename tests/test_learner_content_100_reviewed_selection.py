import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_learner_content_100_reviewed_selection import build
class ReviewedSelectionTests(unittest.TestCase):
 def test_overrides_and_blocked_boundary(self):
  by={x['stable_lexeme_key']:x for x in build()['items']}
  expected={'devoir|VER':'__ws_2_devoir__verb__1','cependant|ADV':'__ws_2_cependant__adv__1','point|NOM':'__ws_7_point__nom__1','corps|NOM':'__ws_2_corps__nom__1','emploi|NOM':'__ws_6_emploi__nom__1','développer|VER':'__ws_3_développer__verb__1','étonner|VER':'__ws_2_étonner__verb__1','rapport|NOM':'__ws_3_rapport__nom__1','paraître|VER':'__ws_4_paraître__verb__1','assurer|VER':'__ws_3_assurer__verb__1','terme|NOM':'__ws_1_terme__nom__2','antenne|NOM':'__ws_6_antenne__nom__1'}
  for key,sense in expected.items(): self.assertEqual(by[key]['primary_learner_sense']['sense_id'],sense)
  self.assertEqual(by['chef|NOM']['primary_learner_sense']['entry_id'],'chef__nom__2')
  self.assertEqual(by['travers|NOM']['selection_status'],'blocked')
if __name__=='__main__': unittest.main()
