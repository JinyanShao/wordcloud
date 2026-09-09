import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import build_phase3_content_draft as draft
class Phase3ContentDraftTests(unittest.TestCase):
 def test_exact_batch_identity_and_review_lines(self):
  rows=json.loads(draft.OUT.read_text())['items']; source=json.loads(draft.INPUT.read_text())['items']; by={x['stable_lexeme_key']:x for x in source}
  self.assertEqual(len(rows),150);self.assertEqual(len(draft.REVIEW.read_text().splitlines()),150)
  for row in rows:self.assertEqual((row['entry_id'],row['sense_id']),(by[row['stable_lexeme_key']]['entry_id'],by[row['stable_lexeme_key']]['sense_id']))
 def test_unreviewed_ai_provenance(self):
  for row in json.loads(draft.OUT.read_text())['items']:
   self.assertEqual(row['content_status'],'ai_draft');self.assertEqual(row['provenance']['actual_model'],'unknown');self.assertFalse(row['used_candidate_refs'])
