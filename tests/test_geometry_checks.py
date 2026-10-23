import unittest
from database.geometry_checks import validate_geometry_cases


class GeometryConsistencyTests(unittest.TestCase):
    def test_rejects_incompatible_historical_congruence_data(self):
        for sides, angles in [([9,8,6],[50,None,None]),
                              ([None,10,7],[45,70,65]),
                              ([6,7,5],[None,58,None]),
                              ([None,7,5],[40,65,None])]:
            with self.subTest(sides=sides, angles=angles):
                with self.assertRaisesRegex(ValueError, 'Inconsistent'):
                    validate_geometry_cases([{'sides':sides,'angles_degrees':angles}])

    def test_accepts_consistent_sas_asa_and_sss_examples(self):
        for sides, angles in [([None,8,6],[50,None,None]),
                              ([None,None,7],[45,70,65]),
                              ([6,7,5],[None,None,None]),
                              ([None,7,5],[40,None,None])]:
            validate_geometry_cases([{'sides':sides,'angles_degrees':angles}])

    def test_rejects_degenerate_and_impossible_measurements(self):
        for sides, angles in [([2,3,5],[None,None,None]),
                              ([None,None,None],[100,90,None]),
                              ([1,float('nan'),2],[None,None,None])]:
            with self.assertRaises(ValueError):
                validate_geometry_cases([{'sides':sides,'angles_degrees':angles}])
