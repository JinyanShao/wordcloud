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
  expected={'devoir|VER':'必须；应该','cependant|ADV':'然而；不过','point|NOM':'点；地点；位置','corps|NOM':'身体；躯体','emploi|NOM':'工作；职位；就业','développer|VER':'发展；使发展','étonner|VER':'使惊讶','rapport|NOM':'关系；关联','chef|NOM':'负责人；领导','paraître|VER':'好像；似乎；看起来','assurer|VER':'确保；保证','terme|NOM':'术语；用语；词','antenne|NOM':'天线','vieux|ADJ':'年长的；年龄较大的','sûr|ADJ':'确定的；无疑的','maison|NOM':'房子；住宅','temps|NOM':'时间；时光','personne|NOM':'人；个人','pouvoir|VER':'能；能够','savoir|VER':'知道；知晓','prendre|VER':'拿；抓取','mettre|VER':'放；放置','remettre|VER':'放回；重新放到原处','élever|VER':'抬高；举起'}
  for key,gloss in expected.items(): self.assertEqual(by[key]['gloss_zh_short'],gloss,key)
  self.assertEqual(by['antenne|NOM']['sense_id'],'__ws_6_antenne__nom__1')
if __name__=='__main__': unittest.main()
