import unittest

from hermes_local_setup.wizard import WizardPage, WizardState


class WizardStateTests(unittest.TestCase):
    def test_complete_flow_has_plain_language_pages(self) -> None:
        state = WizardState()
        visited = [state.page]
        while state.can_advance:
            state = state.advance()
            visited.append(state.page)
        self.assertEqual(
            visited,
            [
                WizardPage.WELCOME,
                WizardPage.PRIVACY,
                WizardPage.SYSTEM_CHECK,
                WizardPage.MODE,
                WizardPage.PROVIDERS,
                WizardPage.OPTIONS,
                WizardPage.REVIEW,
                WizardPage.INSTALL,
                WizardPage.VERIFY,
                WizardPage.FINISH,
            ],
        )

    def test_back_never_moves_before_welcome(self) -> None:
        state = WizardState()
        self.assertEqual(state.back().page, WizardPage.WELCOME)


if __name__ == "__main__":
    unittest.main()
