"""Typed text routing for personal mail and safe plain/HTML composition."""

from copy import deepcopy
import unittest
import test_email_builder as fixture
from emailcenter.email_builder import node, validate_graph, condition_matches
edge = fixture.edge


class BuilderConditionsTests(unittest.TestCase):
    setUp = fixture.BuilderTests.setUp
    tearDown = fixture.BuilderTests.tearDown

    def chain(self):
        data, subject, text, email = self.graph["nodes"]
        condition, merge, tail = node("condition"), node("merge"), node("paragraph")
        condition["config"].update(field="contact.display_name", operator="equals", compare="ada", yes="Hallo {{contact.display_name}}", no="Guten Tag {{company.name}}")
        tail["config"]["text"] = "Mein Anschreiben"
        text["config"]["text"] = "Guten Tag {{company.name}}"
        merge["config"]["separator"] = " · "
        self.graph["nodes"].extend((condition, merge, tail))
        self.graph["edges"] = [e for e in self.graph["edges"] if not (e["to"] == email["id"] and e["input"] == "body")]
        self.graph["edges"].extend((edge(data,"values",condition,"values"), edge(text,"text",condition,"no"), edge(condition,"text",merge,"parts"), edge(tail,"text",merge,"parts"), edge(merge,"text",email,"body")))
        return data, subject, text, email, condition, merge, tail

    def test_personal_branch_and_ordered_merge_preview_and_local_drafts(self):
        *_, condition, merge, tail = self.chain()
        preview = self.service.preview(self.graph)
        self.assertTrue(preview["ready"], preview)
        self.assertEqual(preview["rows"][0]["body"], "Hallo Ada · Mein Anschreiben")
        self.assertEqual(preview["rows"][1]["body"], "Guten Tag Grace GmbH · Mein Anschreiben")
        self.assertEqual(preview["rows"][0]["node_previews"][condition["id"]]["branch"], "yes")
        batch = self.service.create("Textwahl", self.graph, preview["fingerprint"])["batch"]
        self.assertEqual(len(batch["items"]), 2)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM email_jobs").fetchone()[0], 0)

    def test_unselected_text_missing_values_does_not_block_but_selected_does(self):
        data, _, text, _, condition, _, _ = self.chain()
        text["config"]["text"] = "{{extra.required}}"
        condition["config"].update(operator="not_empty")
        preview = self.service.preview(self.graph)
        self.assertTrue(preview["ready"], preview)
        condition["config"]["operator"] = "empty"
        preview = self.service.preview(self.graph)
        self.assertFalse(preview["ready"])
        self.assertIn("extra.required", preview["rows"][0]["error"])

    def test_html_merge_preserves_markup_and_escapes_fields_and_separator(self):
        data, _, _, email, condition, merge, tail = self.chain()
        data["config"]["sources"][0]["fields"]["contact.display_name"] = "<Ada>"
        email["config"]["body_format"] = "html"
        condition["config"].update(operator="not_empty")
        tail["kind"], tail["config"] = "html", {"text": "<b>Anschreiben</b>"}
        merge["config"]["separator"] = " <&>\n"
        value = self.service.preview(self.graph)
        self.assertTrue(value["ready"], value)
        self.assertIn("Hallo &lt;Ada&gt; &lt;&amp;&gt;<br><b>Anschreiben</b>", value["rows"][0]["body"])

    def test_merge_subject_rejects_newlines_and_accepts_explicit_separator(self):
        _, subject, _, email, condition, merge, _ = self.chain()
        self.graph["nodes"].remove(subject)
        self.graph["edges"] = [e for e in self.graph["edges"] if e["to"] != subject["id"] and e["from"] != subject["id"]]
        self.graph["edges"].append(edge(merge,"text",email,"subject"))
        merge["config"]["separator"] = "\n"
        self.assertFalse(self.service.preview(self.graph)["ready"])
        merge["config"]["separator"] = " – "
        self.assertEqual(self.service.preview(self.graph)["rows"][0]["subject"], "Hallo Ada – Mein Anschreiben")

    def test_conditions_validate_and_have_no_expression_execution(self):
        configuration = node("condition")["config"]
        for operator, fields, result in (("empty", {}, True), ("not_empty", {}, False), ("contains", {"contact.display_name":"ADA"}, True), ("not_equals", {"contact.display_name":"Grace"}, True)):
            self.assertEqual(condition_matches({**configuration, "operator":operator, "compare":"ada"},fields), result)
        with self.assertRaisesRegex(ValueError, "fehlt"):
            condition_matches({**configuration,"operator":"equals"}, {})
        condition = node("condition")
        condition["config"]["field"] = "__import__('os')"
        with self.assertRaises(ValueError):
            validate_graph({"nodes":[condition],"edges":[]})
        condition["config"]["field"] = "contact.display_name"
        condition["config"]["operator"] = "execute"
        with self.assertRaises(ValueError):
            validate_graph({"nodes":[condition],"edges":[]},editable=True)

    def test_branch_graph_roundtrips_and_changed_condition_invalidates_capture(self):
        self.chain()
        saved = self.service.save("Bedingungen",self.graph)["version"]
        self.assertEqual(self.service.version(saved["id"])["graph"],self.graph)
        preview = self.service.preview(self.graph)
        next(n for n in self.graph["nodes"] if n["kind"]=="condition")["config"]["compare"]="grace"
        with self.assertRaisesRegex(ValueError,"geändert"):
            self.service.create("Alter Stand",self.graph,preview["fingerprint"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM email_drafts").fetchone()[0],0)
