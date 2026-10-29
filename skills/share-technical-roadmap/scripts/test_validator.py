"""Small positive and negative fixtures for the structural validator."""
import tempfile
import unittest
from pathlib import Path
from validate_drawio import validate

BASE = '''<mxfile><diagram name="Example"><mxGraphModel pageWidth="600" pageHeight="300"><root>
<mxCell id="0"/><mxCell id="1" parent="0"/>
<mxCell id="a" value="Input" vertex="1" parent="1"><mxGeometry x="20" y="20" width="100" height="60"/></mxCell>
<mxCell id="b" value="Output" vertex="1" parent="1"><mxGeometry x="300" y="20" width="100" height="60"/></mxCell>
<mxCell id="e" edge="1" parent="1" source="a" target="b"><mxGeometry relative="1"/></mxCell>
</root></mxGraphModel></diagram></mxfile>'''


class Tests(unittest.TestCase):
    def check_xml(self, xml):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'test.drawio'
            p.write_text(xml)
            return validate(p)['ok']

    def test_native(self):
        self.assertTrue(self.check_xml(BASE))

    def test_dangling(self):
        self.assertFalse(self.check_xml(BASE.replace('target="b"', 'target="unknown"')))

    def test_bounds(self):
        self.assertFalse(self.check_xml(BASE.replace('x="300"', 'x="599"')))

    def test_duplicate(self):
        self.assertFalse(self.check_xml(BASE.replace('id="b"', 'id="a"')))

    def test_flattened(self):
        self.assertFalse(self.check_xml(BASE.replace('value="Input"', 'style="shape=image"')))

    def test_compressed(self):
        self.assertFalse(self.check_xml('<mxfile><diagram>opaque</diagram></mxfile>'))


if __name__ == '__main__':
    unittest.main()
