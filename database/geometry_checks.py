"""Consistency checks for explicitly declared triangle examples."""
import math


def validate_geometry_cases(cases):
    if not isinstance(cases, list):
        raise ValueError('Geometry cases must be a list')
    for case in cases:
        sides = list(case.get('sides', []))
        angles = list(case.get('angles_degrees', []))
        if len(sides) != 3 or len(angles) != 3:
            raise ValueError('Triangle needs three opposite side/angle positions')
        for value in sides + angles:
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value <= 0):
                raise ValueError('Triangle measurements must be positive and finite')
        if any(a is not None and a >= 180 for a in angles):
            raise ValueError('Triangle angle must be less than 180 degrees')
        if sum(a is not None for a in angles) >= 2:
            missing = [i for i, a in enumerate(angles) if a is None]
            if missing:
                angles[missing[0]] = 180 - sum(a for a in angles if a is not None)
            if min(angles) <= 0 or not math.isclose(sum(angles), 180, abs_tol=1e-7):
                raise ValueError('Inconsistent triangle angle sum')
        missing_sides = [i for i, s in enumerate(sides) if s is None]
        if len(missing_sides) == 1:
            i = missing_sides[0]
            if angles[i] is not None:
                j, k = [n for n in range(3) if n != i]
                sides[i] = math.sqrt(sides[j]**2 + sides[k]**2 - 2*sides[j]*sides[k]*math.cos(math.radians(angles[i])))
        if all(s is not None for s in sides):
            if 2*max(sides) >= sum(sides):
                raise ValueError('Triangle inequality failed')
            for i, angle in enumerate(angles):
                if angle is not None:
                    j, k = [n for n in range(3) if n != i]
                    expected = math.degrees(math.acos(max(-1, min(1, (sides[j]**2+sides[k]**2-sides[i]**2)/(2*sides[j]*sides[k])))))
                    if not math.isclose(expected, angle, abs_tol=1e-6):
                        raise ValueError('Inconsistent triangle sides and angles')
        if all(a is not None for a in angles):
            ratios = [side/math.sin(math.radians(angle)) for side, angle in zip(sides, angles) if side is not None]
            if ratios and any(not math.isclose(ratio, ratios[0], rel_tol=1e-7) for ratio in ratios):
                raise ValueError('Inconsistent triangle side/angle ratios')
