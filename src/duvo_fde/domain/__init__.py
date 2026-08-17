"""Domain logic written against the task brief.

This package is intentionally empty in the scaffold. Everything here is written
during the exercise, once the brief is known.

Two rules govern what belongs in this package:

1. **Calculations and business rules live here, on the server.** They are
   deterministic, unit tested, and never delegated to a language model. A model
   that is asked to do arithmetic or apply a threshold will eventually get it
   wrong, silently, on one input out of a hundred.
2. **A fixed business rule is never exposed as a caller-tunable parameter.** If
   the brief states a rule, it is a constant in this package, not an argument a
   caller can override.
"""

__all__: list[str] = []
