import pytest


class _PytestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def ok(self, name):
        self.passed += 1
        print(f"  PASS  {name}")

    def fail(self, name, reason):
        self.failed += 1
        self.errors.append((name, reason))
        print(f"  FAIL  {name}: {reason}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n  Results: {self.passed}/{total} passed, {self.failed} failed")
        if self.errors:
            print("  Failures:")
            for name, reason in self.errors:
                print(f"    - {name}: {reason}")
        return self.failed == 0


@pytest.fixture
def r():
    return _PytestResults()
