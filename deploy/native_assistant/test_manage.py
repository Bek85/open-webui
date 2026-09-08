import unittest

from manage import MAIN_ID, PUBLIC_READ, TOOL_ID, native_model


class ModelConfigurationTests(unittest.TestCase):
    def test_public_means_authenticated_not_anonymous(self):
        self.assertEqual(PUBLIC_READ, [{'principal_type': 'user', 'principal_id': '*', 'permission': 'read'}])

    def test_required_tools_and_grounded_files(self):
        model = native_model(MAIN_ID, public=True)
        self.assertEqual(model['meta']['requiredToolIds'], [TOOL_ID])
        self.assertEqual(model['meta']['toolIds'], [TOOL_ID])
        self.assertTrue(model['meta']['capabilities']['file_context'])
        self.assertFalse(model['meta']['capabilities']['vision'])

    def test_canary_stays_private(self):
        self.assertEqual(native_model('prokuratura_native_canary')['access_grants'], [])


if __name__ == '__main__':
    unittest.main()
