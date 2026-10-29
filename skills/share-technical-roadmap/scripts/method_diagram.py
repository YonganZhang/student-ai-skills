"""Build, render and check a native methodology diagram; never establishes scientific validity."""
import argparse
import asyncio
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import tarfile
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from validate_drawio import validate

PACKAGE_URL = "https://registry.npmjs.org/mxgraph/-/mxgraph-4.2.2.tgz"
PACKAGE_SHA1 = "52336443f10ab1039be79cc3fdd2eb8c00c91ba2"
JAVASCRIPT_SHA256 = "99da390e20b4f3f0130a0d73b86bcbec011b5c187eef333521fc08fb5ba7582e"
ROLES = {"input": ("#edf3f8", "#9cb6c8"), "core": ("#edf3f8", "#9cb6c8"),
         "output": ("#edf3f8", "#9cb6c8"), "extension": ("#e8f4ef", "#75a994"),
         "reference": ("#f1f3f5", "#a6b1bb"), "pending": ("#fff4df", "#cfaa65")}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def project_file(project, name):
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Source/spec paths must be project-relative without parent traversal")
    resolved = (project / path).resolve()
    if not resolved.is_relative_to(project) or not resolved.is_file():
        raise ValueError(f"Missing or out-of-project source: {name}")
    return resolved


def numbers(value, count):
    return isinstance(value, list) and len(value) == count and all(
        isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in value)


def load_spec(project, spec_path):
    spec_file = project_file(project, spec_path)
    raw = spec_file.read_bytes()
    spec = json.loads(raw)
    if spec.get("schema_version") != 1 or not isinstance(spec.get("title"), str) or not spec["title"].strip():
        raise ValueError("Expected schema_version=1 and a nonempty title")
    if not isinstance(spec.get("caption"), str) or not isinstance(spec.get("sources"), list) or not spec["sources"]:
        raise ValueError("Expected a caption and nonempty project-relative sources")
    sources = []
    for name in spec["sources"]:
        if not isinstance(name, str):
            raise ValueError("Source names must be strings")
        sources.append({"path": name, "sha256": digest(project_file(project, name).read_bytes())})
    nodes, edges = spec.get("nodes"), spec.get("edges")
    if not isinstance(nodes, list) or not nodes or not isinstance(edges, list):
        raise ValueError("Expected nonempty nodes and an edges list")
    ids = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise ValueError("Nodes must be objects")
        key = node.get("id")
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", key) or key in ids:
            raise ValueError("Node IDs must be unique simple names")
        if node.get("role") not in ROLES or not isinstance(node.get("label"), str) or not node["label"].strip():
            raise ValueError("Each node needs a label and known semantic role")
        bounds = node.setdefault("bounds", [60 + index % 3 * 490, 160 + index // 3 * 250, 360, 110])
        if not numbers(bounds, 4) or min(bounds[:2]) < 0 or min(bounds[2:]) <= 0:
            raise ValueError("Node bounds require finite nonnegative x/y and positive width/height")
        ids.add(key)
    edge_ids = set()
    for edge in edges:
        if not isinstance(edge, dict):
            raise ValueError("Edges must be objects")
        key = edge.get("id")
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", key) or key in edge_ids or key in ids:
            raise ValueError("Edge IDs must be unique simple names distinct from nodes")
        if edge.get("source") not in ids or edge.get("target") not in ids:
            raise ValueError("Edge endpoint does not identify a node")
        if edge.get("kind") not in {"flow", "pending", "reference"} or not isinstance(edge.get("label"), str) or not edge["label"].strip():
            raise ValueError("Each edge needs a transfer label and explicit flow/pending/reference kind")
        ports = edge.setdefault("ports", [1, .5, 0, .5])
        if not numbers(ports, 4) or not all(0 <= x <= 1 for x in ports):
            raise ValueError("Ports must contain four values in [0,1]")
        if not isinstance(edge.get("via", []), list) or not all(numbers(p, 2) and min(p) >= 0 for p in edge.get("via", [])):
            raise ValueError("Waypoints must contain nonnegative finite x/y pairs")
        edge_ids.add(key)
    return spec_file, raw, spec, sources


def build(project, spec_path, out_dir):
    spec_file, raw, spec, sources = load_spec(project, spec_path)
    out = (project / out_dir).resolve()
    if not out.is_relative_to(project) or out == project:
        raise ValueError("Output directory must be inside the project")
    if out.exists() and any(out.iterdir()):
        raise ValueError("Output directory must be empty; preserve approved diagrams and prior evidence")
    out.mkdir(parents=True, exist_ok=True)
    points = [point for edge in spec["edges"] for point in edge.get("via", [])]
    width = max([1460] + [n["bounds"][0] + n["bounds"][2] + 60 for n in spec["nodes"]] + [p[0] + 60 for p in points])
    height = max([760] + [n["bounds"][1] + n["bounds"][3] + 200 for n in spec["nodes"]] + [p[1] + 200 for p in points])
    mx = ET.Element("mxfile")
    diagram = ET.SubElement(mx, "diagram", id="method", name=spec["title"])
    model = ET.SubElement(diagram, "mxGraphModel", page="1", pageWidth=str(width), pageHeight=str(height), background="#ffffff")
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", id="0")
    ET.SubElement(root, "mxCell", id="1", parent="0")
    def vertex(key, label, bounds, style):
        cell = ET.SubElement(root, "mxCell", id=key, value=label, style=style, vertex="1", parent="1")
        ET.SubElement(cell, "mxGeometry", **dict(zip(["x", "y", "width", "height"], map(str, bounds))), **{"as": "geometry"})
    text_style = "text;html=0;whiteSpace=wrap;align=left;verticalAlign=middle;strokeColor=none;fillColor=none;fontFamily=Noto Sans CJK SC;"
    vertex("__title", spec["title"], [60, 30, width - 120, 64], text_style + "fontSize=32;fontColor=#183344;")
    for node in spec["nodes"]:
        fill, stroke = ROLES[node["role"]]
        vertex(node["id"], node["label"], node["bounds"], "rounded=1;arcSize=10;html=0;whiteSpace=wrap;align=center;verticalAlign=middle;spacing=12;fontFamily=Noto Sans CJK SC;fontSize=23;fontColor=#183344;strokeWidth=1.5;" + f"fillColor={fill};strokeColor={stroke};")
    for edge in spec["edges"]:
        ports = ";".join(f"{name}={value}" for name, value in zip(["exitX", "exitY", "entryX", "entryY"], edge["ports"])) + ";"
        line = {"flow": "strokeColor=#708995;endArrow=block;endFill=1;", "pending": "strokeColor=#b07b25;dashed=1;dashPattern=6 5;endArrow=block;endFill=1;", "reference": "strokeColor=#8996a1;dashed=1;dashPattern=2 4;endArrow=open;endFill=0;"}[edge["kind"]]
        cell = ET.SubElement(root, "mxCell", id=edge["id"], value=edge["label"], source=edge["source"], target=edge["target"], edge="1", parent="1", style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=0;strokeWidth=2;labelBackgroundColor=#ffffff;fontFamily=Noto Sans CJK SC;fontSize=18;fontColor=#445665;" + ports + line)
        geometry = ET.SubElement(cell, "mxGeometry", relative="1", **{"as": "geometry"})
        if edge.get("via"):
            points = ET.SubElement(geometry, "Array", **{"as": "points"})
            for x, y in edge["via"]:
                ET.SubElement(points, "mxPoint", x=str(x), y=str(y))
    vertex("__legend", "实线：定义明确的计算关系；虚线：待确定接入；点线：参照约束。线型不表示运行/验证完成。", [60, height - 120, width - 120, 44], text_style + "fontSize=18;fontColor=#536575;")
    vertex("__caption", spec["caption"], [60, height - 70, width - 120, 46], text_style + "fontSize=18;fontColor=#536575;")
    ET.indent(mx, space="  ")
    target = out / "diagram.drawio"
    ET.ElementTree(mx).write(target, encoding="utf-8", xml_declaration=True)
    structural = validate(target)
    if not structural["ok"]:
        raise ValueError("Native diagram structure failed: " + "; ".join(structural["errors"]))
    manifest = {"schema_version": 1, "kind": "method-diagram-derived-view", "spec": {"path": str(spec_file.relative_to(project)), "sha256": digest(raw)},
                "sources": sources, "artifacts": {target.name: digest(target.read_bytes())}, "rendered": False,
                "meaning": "Defined interfaces, not proof of implementation, execution, or validation"}
    dump(out / "manifest.json", manifest)
    return {"ok": True, "out_dir": str(out), "nodes": len(spec["nodes"]), "edges": len(spec["edges"]), "rendered": False}


def load_manifest(path):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or manifest.get("kind") != "method-diagram-derived-view":
        raise ValueError("Not a generated method-diagram manifest")
    def valid_source(item):
        return (isinstance(item, dict) and isinstance(item.get("path"), str) and item["path"].strip()
                and isinstance(item.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", item["sha256"]))
    if not valid_source(manifest.get("spec")) or not isinstance(manifest.get("sources"), list) or not manifest["sources"] or not all(valid_source(item) for item in manifest["sources"]):
        raise ValueError("Manifest requires a valid spec and nonempty source hashes")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts or not isinstance(manifest.get("rendered"), bool):
        raise ValueError("Manifest requires artifact hashes and an explicit rendered boolean")
    required = {"diagram.drawio", "diagram.png", "diagram.svg"} if manifest["rendered"] else {"diagram.drawio"}
    if not required.issubset(artifacts):
        raise ValueError("Manifest is missing required artifacts: " + ", ".join(sorted(required - artifacts.keys())))
    for name, value in artifacts.items():
        if Path(name).name != name or not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("Artifact entries require local basenames and SHA256 hashes")
    return manifest


def runtime_javascript(cache_dir):
    cache_dir.mkdir(parents=True, exist_ok=True)
    js = cache_dir / "mxClient-4.2.2.js"
    if not js.exists():
        with urllib.request.urlopen(PACKAGE_URL, timeout=60) as response:
            raw = response.read()
        if hashlib.sha1(raw).hexdigest() != PACKAGE_SHA1:
            raise ValueError("Pinned mxGraph package hash mismatch")
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
            js.write_bytes(archive.extractfile("package/javascript/mxClient.js").read())
    if digest(js.read_bytes()) != JAVASCRIPT_SHA256:
        raise ValueError("Pinned mxGraph JavaScript hash mismatch")
    return js


async def export_image_files(diagram, js, output):
    from playwright.async_api import async_playwright
    xml = diagram.read_text(encoding="utf-8")
    if len(ET.fromstring(xml).findall("diagram")) != 1:
        raise ValueError("This renderer exports one page; use a multipage draw.io exporter")
    model = ET.fromstring(xml).find("diagram/mxGraphModel")
    width, height = math.ceil(float(model.get("pageWidth"))), math.ceil(float(model.get("pageHeight")))
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            page = await browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1.5)
            await page.route("**/*", lambda route: route.abort())
            await page.set_content(f'<html><style>body{{margin:0;background:white}}#graph{{width:{width}px;height:{height}px}}</style><body><div id="graph"></div></body></html>')
            await page.evaluate("window.mxLoadResources=false;window.mxLoadStylesheets=false;")
            await page.add_script_tag(path=str(js))
            await page.evaluate("""(xml) => {
                const doc=mxUtils.parseXml(xml), model=doc.getElementsByTagName('mxGraphModel')[0];
                const graph=new mxGraph(document.getElementById('graph'));
                graph.setEnabled(false);graph.setHtmlLabels(false);
                new mxCodec(model.ownerDocument).decode(model,graph.getModel());graph.refresh();
            }""", xml)
            await page.evaluate("document.fonts.ready")
            await page.locator("#graph").screenshot(path=str(output / "diagram.png"))
            svg = await page.evaluate("""([w,h]) => {
                const svg=document.querySelector('#graph svg').cloneNode(true);
                svg.setAttribute('xmlns','http://www.w3.org/2000/svg');svg.setAttribute('width',w);svg.setAttribute('height',h);
                svg.setAttribute('viewBox',`0 0 ${w} ${h}`);return new XMLSerializer().serializeToString(svg);
            }""", [width, height])
            (output / "diagram.svg").write_text(svg, encoding="utf-8")
        finally:
            await browser.close()


def publish_render(staged, output):
    # No overwrite of image files. Roll back only files created by this invocation.
    # Not a concurrent-writer transaction; callers must use separate revision directories.
    created = []
    try:
        for name in ["diagram.png", "diagram.svg"]:
            target = output / name
            os.link(staged / name, target)
            created.append(target)
        os.replace(staged / "manifest.json", output / "manifest.json")
    except Exception:
        for target in created:
            target.unlink()
        raise


async def render(diagram, cache_dir):
    diagram = diagram.resolve()
    structural = validate(diagram)
    if not structural["ok"]:
        raise ValueError("Invalid native diagram")
    manifest_path = diagram.parent / "manifest.json"
    manifest = load_manifest(manifest_path)
    if manifest["artifacts"].get(diagram.name) != digest(diagram.read_bytes()):
        raise ValueError("Diagram differs from its generation manifest; preserve/review edits before export")
    if any((diagram.parent / name).exists() for name in ["diagram.png", "diagram.svg"]):
        raise ValueError("Rendered outputs already exist; use a new diagram revision")
    js = runtime_javascript(cache_dir)
    with tempfile.TemporaryDirectory(prefix=".method-render-", dir=diagram.parent) as temporary:
        staged = Path(temporary)
        await export_image_files(diagram, js, staged)
        manifest["artifacts"].update({name: digest((staged / name).read_bytes()) for name in ["diagram.png", "diagram.svg"]})
        manifest.update({"rendered": True, "renderer": {"name": "official jgraph/mxgraph 4.2.2 + browser SVG", "package_url": PACKAGE_URL, "package_sha1": PACKAGE_SHA1, "javascript_sha256": JAVASCRIPT_SHA256}, "visual_review": "required; not performed by this renderer"})
        dump(staged / "manifest.json", manifest)
        publish_render(staged, diagram.parent)
    return {"ok": True, "rendered": True, "visual_review_required": True, "out_dir": str(diagram.parent)}


def check(project, manifest_path):
    manifest = load_manifest(manifest_path)
    issues = []
    for name in ["diagram.png", "diagram.svg"]:
        if (manifest_path.parent / name).exists() and name not in manifest["artifacts"]:
            issues.append({"kind": "unlisted_artifact", "path": name})
    for item in [manifest["spec"]] + manifest["sources"]:
        try:
            current = digest(project_file(project, item["path"]).read_bytes())
        except (OSError, ValueError):
            current = None
        if current != item["sha256"]:
            issues.append({"kind": "source_drift", "path": item["path"]})
    for name, expected in manifest["artifacts"].items():
        if Path(name).name != name:
            raise ValueError("Artifact names must be local basenames")
        path = manifest_path.parent / name
        if not path.is_file() or digest(path.read_bytes()) != expected:
            issues.append({"kind": "artifact_drift", "path": name})
    return {"ok": not issues, "rendered": manifest.get("rendered", False), "issues": issues,
            "scope": "file freshness only; no scientific or visual correctness claim"}


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog="Example: method_diagram.py build --project . --spec method.json --out-dir _figures/method-r1")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("build", epilog="Example: build --project . --spec method.json --out-dir _figures/method-r1")
    p.add_argument("--project", type=Path, default=Path.cwd())
    p.add_argument("--spec", required=True)
    p.add_argument("--out-dir", required=True)
    p = commands.add_parser("render", epilog="Example: render --diagram _figures/method-r1/diagram.drawio")
    p.add_argument("--diagram", type=Path, required=True)
    p.add_argument("--cache-dir", type=Path)
    p = commands.add_parser("check", epilog="Example: check --project . --manifest _figures/method-r1/manifest.json")
    p.add_argument("--project", type=Path, default=Path.cwd())
    p.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "build":
            result = build(args.project.resolve(), args.spec, args.out_dir)
        elif args.command == "check":
            result = check(args.project.resolve(), args.manifest.resolve())
        elif args.cache_dir:
            result = asyncio.run(render(args.diagram, args.cache_dir.resolve()))
        else:
            with tempfile.TemporaryDirectory(prefix="method-render-") as cache:
                result = asyncio.run(render(args.diagram, Path(cache)))
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["ok"] else 1
    except Exception as exc:
        # CLI boundary includes optional browser/network failures; never returns a success marker.
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        print(f"method_diagram: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2 if isinstance(exc, (ValueError, TypeError, KeyError)) else 1


if __name__ == "__main__":
    sys.exit(main())
