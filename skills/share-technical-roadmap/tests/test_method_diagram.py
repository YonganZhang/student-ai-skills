"""User-visible contracts: editable output, no clobber, source drift and flexible graph shape."""
import copy
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
import method_diagram as tool


class MethodDiagramTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        source = self.root / "_wiki-methodology/_wiki/_methods/method.md"
        source.parent.mkdir(parents=True)
        source.write_text("# Example method\nA stated input maps to a stated output.\n")
        self.spec = json.loads((SKILL / "assets/method-framework.json").read_text())
        self.path = self.root / "method.json"
        self.write_spec()

    def tearDown(self):
        self.temp.cleanup()

    def write_spec(self):
        self.path.write_text(json.dumps(self.spec, ensure_ascii=False))

    def build(self):
        return tool.build(self.root, "method.json", "figures/r1")

    def test_native_roles_and_unresolved_edges(self):
        result = self.build()
        self.assertEqual((result["nodes"], result["edges"]), (6, 6))
        model = ET.parse(self.root / "figures/r1/diagram.drawio")
        cells = {v.get("id"): v for v in model.iter("mxCell")}
        self.assertIn("dashed=1", cells["extension_candidate"].get("style"))
        self.assertIn("endArrow=open", cells["output_candidate"].get("style"))
        self.assertTrue(all(v.get("source") != "reference" for v in cells.values()))
        self.assertTrue(tool.check(self.root, self.root / "figures/r1/manifest.json")["ok"])
        self.assertFalse(result["rendered"])

    def test_source_change_is_reported_as_stale(self):
        self.build()
        (self.root / self.spec["sources"][0]).write_text("Changed method meaning")
        result = tool.check(self.root, self.root / "figures/r1/manifest.json")
        self.assertFalse(result["ok"])
        self.assertEqual(result["issues"], [{"kind": "source_drift", "path": self.spec["sources"][0]}])

    def test_spec_change_is_reported_as_stale(self):
        self.build()
        self.spec["nodes"][0]["label"] = "Changed input"
        self.write_spec()
        self.assertFalse(tool.check(self.root, self.root / "figures/r1/manifest.json")["ok"])

    def test_manual_output_change_is_not_silently_rebuilt(self):
        self.build()
        path = self.root / "figures/r1/diagram.drawio"
        original = path.read_text()
        path.write_text(original + "<!-- manual edit -->")
        self.assertFalse(tool.check(self.root, path.with_name("manifest.json"))["ok"])
        with self.assertRaises(ValueError):
            self.build()
        self.assertTrue(path.read_text().endswith("<!-- manual edit -->"))

    def test_missing_source_rejected(self):
        self.spec["sources"] = ["missing.md"]
        self.write_spec()
        with self.assertRaises(ValueError):
            self.build()

    def test_escape_source_rejected(self):
        self.spec["sources"] = ["../private.md"]
        self.write_spec()
        with self.assertRaises(ValueError):
            self.build()

    def test_dangling_edge_and_unknown_semantics_rejected(self):
        for key, value in [("target", "missing"), ("kind", "already_verified")]:
            spec = copy.deepcopy(self.spec)
            spec["edges"][0][key] = value
            self.path.write_text(json.dumps(spec))
            with self.assertRaises(ValueError):
                self.build()

    def test_small_chain_does_not_require_six_nodes(self):
        self.spec["nodes"] = [dict(v) for v in self.spec["nodes"][:3]]
        for v in self.spec["nodes"]:
            v.pop("bounds")
        self.spec["edges"] = self.spec["edges"][:2]
        self.write_spec()
        result = self.build()
        self.assertEqual((result["nodes"], result["edges"]), (3, 2))

    def test_incomplete_manifest_never_claims_fresh_render(self):
        self.build()
        path = self.root / "figures/r1/manifest.json"
        original = json.loads(path.read_text())
        cases = [dict(original, artifacts={}), dict(original, rendered=True), dict(original, sources=[])]
        for invalid in cases:
            path.write_text(json.dumps(invalid))
            with self.assertRaises(ValueError):
                tool.check(self.root, path)

    def test_partial_unlisted_render_is_not_fresh(self):
        self.build()
        path = self.root / "figures/r1/manifest.json"
        path.with_name("diagram.png").write_bytes(b"partial render")
        result = tool.check(self.root, path)
        self.assertFalse(result["ok"])
        self.assertIn({"kind": "unlisted_artifact", "path": "diagram.png"}, result["issues"])

    def test_render_failure_preserves_manifest_and_allows_retry(self):
        self.build()
        out = self.root / "figures/r1"
        original = (out / "manifest.json").read_bytes()
        async def write_then_fail(diagram, js, staged):
            (staged / "diagram.png").write_bytes(b"interrupted png")
            raise RuntimeError("browser failed after screenshot")
        async def export_stub(diagram, js, staged):
            (staged / "diagram.png").write_bytes(b"png fixture, transaction test only")
            (staged / "diagram.svg").write_text("<svg/>")
        with mock.patch.object(tool, "runtime_javascript", return_value=self.root / "unused.js"):
            with mock.patch.object(tool, "export_image_files", side_effect=write_then_fail):
                with self.assertRaises(RuntimeError):
                    asyncio.run(tool.render(out / "diagram.drawio", self.root / "cache"))
            self.assertEqual((out / "manifest.json").read_bytes(), original)
            self.assertFalse((out / "diagram.png").exists())
            with mock.patch.object(tool, "export_image_files", side_effect=export_stub):
                with mock.patch.object(tool.os, "replace", side_effect=PermissionError("manifest publish denied")):
                    with self.assertRaises(PermissionError):
                        asyncio.run(tool.render(out / "diagram.drawio", self.root / "cache"))
                self.assertEqual((out / "manifest.json").read_bytes(), original)
                self.assertFalse((out / "diagram.png").exists())
                self.assertFalse((out / "diagram.svg").exists())
                asyncio.run(tool.render(out / "diagram.drawio", self.root / "cache"))
        self.assertTrue(tool.check(self.root, out / "manifest.json")["ok"])
        self.assertFalse(list(out.glob(".method-render-*")))

    def test_waypoints_expand_canvas_instead_of_clipping(self):
        self.spec["edges"][0]["via"] = [[2000, 900]]
        self.write_spec()
        self.build()
        model = ET.parse(self.root / "figures/r1/diagram.drawio").find("diagram/mxGraphModel")
        self.assertGreater(float(model.get("pageWidth")), 2000)
        self.assertGreater(float(model.get("pageHeight")), 900)

    def test_output_cannot_escape_project(self):
        with self.assertRaises(ValueError):
            tool.build(self.root, "method.json", "../outside-method-output")

    def test_cli_exit_codes_and_json_freshness(self):
        command = [sys.executable, str(SKILL / "scripts/method_diagram.py")]
        run = subprocess.run(command + ["build", "--project", str(self.root), "--spec", "method.json", "--out-dir", "figures/r1"], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(json.loads(run.stdout)["ok"])
        manifest = self.root / "figures/r1/manifest.json"
        self.path.write_text("{}")
        run = subprocess.run(command + ["check", "--project", str(self.root), "--manifest", str(manifest)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 1, run.stderr)
        self.assertFalse(json.loads(run.stdout)["ok"])
        run = subprocess.run(command + ["build", "--project", str(self.root), "--spec", "method.json", "--out-dir", "figures/r2"], capture_output=True, text=True)
        self.assertEqual(run.returncode, 2, run.stderr)
        self.assertFalse(json.loads(run.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
