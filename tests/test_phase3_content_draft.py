import json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import build_phase3_content_draft as draft
class Phase3ContentDraftTests(unittest.TestCase):
 def setUp(self):self.rows=json.loads(draft.OUT.read_text())['items'];self.by={x['stable_lexeme_key']:x for x in self.rows}
 def test_exact_authoritative_binding(self):
  source={x['stable_lexeme_key']:x for x in json.loads(draft.INPUT.read_text())['items']}
  self.assertEqual(len(self.rows),150)
  for key,row in self.by.items():self.assertEqual((row['entry_id'],row['sense_id']),(source[key]['entry_id'],source[key]['sense_id']))
 def test_grammar_sensitive_external_authoring_is_preserved(self):
  self.assertEqual(self.by['concerner|VER']['example_fr'],'Cette règle concerne tous les étudiants.')
  self.assertIn('s’exclame',self.by['exclamer|VER']['example_fr'])
  self.assertIn('disposons de',self.by['disposer|VER']['example_fr'])
  self.assertIn('appartient à',self.by['appartenir|VER']['example_fr'])
  self.assertIn('父亲',self.by['père|NOM']['gloss_zh_short'])
  self.assertIn('黄金',self.by['or|NOM']['gloss_zh_short'])
  self.assertIn('可行',self.by['possible|ADJ']['gloss_zh_short'])
 def test_no_template_generation_in_packager(self):
  text=Path(draft.__file__).read_text()
  self.assertNotIn('def example(',text);self.assertNotIn('def article(',text);self.assertNotIn('GLOSS={',text)
