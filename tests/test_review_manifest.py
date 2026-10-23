import json
import unittest
from database import ROOT, digest
from database.importer import stable
from database.theory_content import validate_release


class ReviewManifestTests(unittest.TestCase):
    def test_review_is_complete_current_and_not_teacher_certification(self):
        manifest=json.loads((ROOT/'content/theory/review-manifest.json').read_text(encoding='utf-8'))
        catalog=json.loads((ROOT/'curriculum/catalog-2026-2027.json').read_text(encoding='utf-8'))
        units={u['id']:u for u in catalog['units']}
        records={u['unit_id']:u for u in manifest['units']}
        self.assertEqual(len(records),len(manifest['units']))
        self.assertEqual(set(records),set(units))
        self.assertEqual(manifest['educator_approved_units'],0)
        for record in records.values():
            self.assertEqual(record['educator_review'],'pending')
            self.assertEqual(record['source_refs'],units[record['unit_id']]['source_refs'])
            file=ROOT/'content/theory'/record['release_file']
            release=json.loads(file.read_text(encoding='utf-8'))
            matching=[(u,b) for u,_,b in validate_release(release) if u['id']==record['unit_id']]
            self.assertEqual(len(matching),1)
            unit,blocks=matching[0]
            self.assertEqual(record['content_hash'],digest(blocks))
            self.assertEqual(record['theory_version_id'],stable('theory-version/'+unit['id']+'/'+digest(blocks)))
