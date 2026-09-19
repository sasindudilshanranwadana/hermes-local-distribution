import unittest


class PackageTests(unittest.TestCase):
    def test_package_exposes_alpha_version(self) -> None:
        import hermes_local_setup

        self.assertEqual(hermes_local_setup.__version__, "0.1.0a1")


if __name__ == "__main__":
    unittest.main()

