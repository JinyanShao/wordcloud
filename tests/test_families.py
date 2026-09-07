"""Protect family boundaries and unknown derivation directions."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_families import audit

class FamilyAuditTests(unittest.TestCase):
    def runtime(self, edges):
        return {'nodes': [[i, str(i), 'NOM', 'B1', 'hint'] for i in range(1, 5)],
                'official_edges': edges, 'senses': {'1': [{'senses': [{}]}]}}

    def edge(self, a, b, review='sourced', direction=''):
        return [a,b,'fam','derivational_morphology','conversion',direction,'词性转换','',.98,review]

    def test_editorial_and_similarity_do_not_join_sourced_families(self):
        editorial=self.edge(2,3,'editorial_reviewed')
        similarity=self.edge(3,4);similarity[2]='syn'
        result=audit(self.runtime([self.edge(1,2),editorial,similarity]))
        self.assertEqual((result['partial_families'],result['family_words']), (1,2))

    def test_transitive_membership_and_missing_definition_remain_visible(self):
        result=audit(self.runtime([self.edge(1,2),self.edge(2,3)]))
        self.assertEqual(result['largest_family'],3)
        self.assertEqual(result['family_words_with_french_senses'],1)
        self.assertEqual(result['families_with_all_members_defined'],0)
        self.assertEqual(result['patterns'][0]['from_pos'],'undirected')

    def test_direction_must_use_the_actual_endpoints(self):
        with self.assertRaises(AssertionError):
            audit(self.runtime([self.edge(1,2,direction='1->3')]))

if __name__ == '__main__': unittest.main()
