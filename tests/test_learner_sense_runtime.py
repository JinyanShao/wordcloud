import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_learner_sense_runtime import build
class LearnerSenseRuntimeTests(unittest.TestCase):
 def test_phase2c_and_phase3_records_enter_runtime(self):
  payload=build(); rows=payload['records']
  self.assertEqual(len(rows),598)
  self.assertEqual(sum(x['cohort']=='phase2c' for x in rows),99)
  self.assertEqual(sum(x['cohort']=='phase3' for x in rows),499)
  self.assertFalse(any(x['stable_lexeme_key'] in {'travers|NOM','cesse|NOM'} for x in rows))
 def test_exact_regression_senses_are_projected(self):
  by={x['stable_lexeme_key']:x for x in build()['records']}
  expected={'devoir|VER':'必须；应该','cependant|ADV':'然而；不过','point|NOM':'点；地点；位置','corps|NOM':'身体；躯体','emploi|NOM':'工作；职位；就业','développer|VER':'发展；使发展','étonner|VER':'使惊讶','rapport|NOM':'关系；关联','chef|NOM':'负责人；领导','paraître|VER':'好像；似乎；看起来','assurer|VER':'确保；保证','terme|NOM':'术语；用语；词','antenne|NOM':'天线','vieux|ADJ':'年长的；年龄较大的','sûr|ADJ':'确定的；无疑的','maison|NOM':'房子；住宅','temps|NOM':'时间；时光','personne|NOM':'人；个人','pouvoir|VER':'能；能够','savoir|VER':'知道；知晓','prendre|VER':'拿；抓取','mettre|VER':'放；放置','remettre|VER':'放回；重新放到原处','élever|VER':'抬高；举起'}
  for key,gloss in expected.items(): self.assertEqual(by[key]['gloss_zh_short'],gloss,key)
  self.assertEqual(by['antenne|NOM']['sense_id'],'__ws_6_antenne__nom__1')
 def test_phase3_v2_corrections_are_projected(self):
  by={x['stable_lexeme_key']:x for x in build()['records']}
  expected={'langue|NOM':'__ws_4_langue__nom__1','peau|NOM':'__ws_1_peau__nom__1','émission|NOM':'__ws_2_émission__nom__1','appeler|VER':'__ws_22_appeler__verb__1','impression|NOM':'__ws_7_impression__nom__1','évoquer|VER':'__ws_4_évoquer__verb__1','illustrer|VER':'__ws_3_illustrer__verb__1','engager|VER':'__ws_6_engager__verb__1'}
  for key,sense in expected.items():self.assertEqual(by[key]['sense_id'],sense)
if __name__=='__main__': unittest.main()
