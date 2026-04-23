from .a_gel_algebra import theory as a_gel_algebra_theory
from .c_epal import theory as c_epal_theory

theory_map = {
    ("a-gel", "algebra"): a_gel_algebra_theory,
    ("g-epal", "algebra"): c_epal_theory,
}