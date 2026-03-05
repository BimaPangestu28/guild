import unittest
from git_workflow import generate_branch_name

class TestGitWorkflow(unittest.TestCase):
    def test_generate_branch_name(self):
        name = generate_branch_name("feature", "ABC123", "Add user authentication")
        self.assertEqual(name, "feature/GLD-ABC123-add-user-authentication")

    def test_branch_name_long_title(self):
        name = generate_branch_name("bugfix", "DEF456", "Fix the very long bug description that should be truncated to forty characters")
        self.assertTrue(len(name.split("/")[1]) <= 60)  # GLD-DEF456- prefix + 40 chars max
        self.assertTrue(name.startswith("bugfix/GLD-DEF456-"))

    def test_branch_name_special_chars(self):
        name = generate_branch_name("feature", "GHI789", "Add @user auth & fix #123")
        self.assertNotIn("@", name)
        self.assertNotIn("&", name)
        self.assertNotIn("#", name)

if __name__ == '__main__':
    unittest.main()
