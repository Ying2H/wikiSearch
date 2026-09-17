import unittest

from search_sync.sync.classifier import classify_source


class ClassifierTests(unittest.TestCase):
    def test_direct_listpages_is_dynamic(self):
        result = classify_source('[[module ListPages category="*"]]')

        self.assertEqual(result.dynamic_class, "dynamic-listpages")
        self.assertIn("direct-listpages", result.reasons)

    def test_include_creates_transitive_dependency(self):
        result = classify_source("[[include component:nav]]")

        self.assertEqual(result.dynamic_class, "dynamic-transitive")
        self.assertEqual(result.includes, ("component:nav",))

    def test_parameterized_include_is_unknown(self):
        result = classify_source("[[include component:nav | mode=compact]]")

        self.assertEqual(result.dynamic_class, "unknown")
        self.assertEqual(result.parameterized_includes, ("component:nav",))

    def test_css_module_is_not_marked_dynamic(self):
        result = classify_source("[[module CSS]]\nbody { color: red; }")

        self.assertEqual(result.dynamic_class, "static")

    def test_unresolved_content_token_is_unknown(self):
        result = classify_source("---\n[[content]]\n---")

        self.assertEqual(result.dynamic_class, "unknown")
        self.assertIn("unresolved-content-token", result.reasons)

    def test_yaml_like_data_form_source_is_unknown(self):
        result = classify_source("full_egg: 'Anomalous Siniperca'\ntitle: '一条鳜鱼'\nanswer: ''")

        self.assertEqual(result.dynamic_class, "unknown")
        self.assertIn("yaml-like-data-form-source", result.reasons)
