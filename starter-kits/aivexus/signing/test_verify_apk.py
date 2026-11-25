import unittest
from verify_apk import validate_identity

CERT = "ab" * 32
GOOD = "package: name='com.aivexus.demo' versionCode='3' versionName='0.1.1'\n"
SIGN = "Signer #1 certificate SHA-256 digest: " + CERT


class IdentityTests(unittest.TestCase):
    def check(self, badging=GOOD, certs=SIGN, package="com.aivexus.demo", code=3, previous=2, expected=CERT):
        validate_identity(badging, certs, package, code, previous, expected)

    def test_good(self):
        self.check()

    def test_bad_identity(self):
        for kwargs in ({"package": "com.aivexus.other"}, {"code": 4}, {"previous": 3},
                       {"expected": "cd" * 32}, {"certs": ""}, {"expected": ""},
                       {"badging": GOOD + "application-debuggable\n"},
                       {"certs": SIGN + "\nSigner #2 certificate SHA-256 digest: " + "cd" * 32}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.check(**kwargs)


if __name__ == "__main__":
    unittest.main()
