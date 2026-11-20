"""作者 Wangyuan，2026-11-20。用自建的文字层 PDF 验证可选读取路径。"""
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path

from simulation.text_processing import extract_text_from_file


def synthetic_pdf() -> bytes:
    """构造一页带文字和有效交叉引用表的最小 PDF。"""
    stream = b"BT /F1 12 Tf 40 60 Td (Synthetic project context.) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
    ]
    result = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    start = len(result)
    result.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for offset in offsets:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode())
    return bytes(result)


class PdfOptionalTest(unittest.TestCase):
    @unittest.skipUnless(find_spec("pdfminer"), "需安装可选的 requirements-pdf.txt")
    def test_synthetic_text_layer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.pdf"
            path.write_bytes(synthetic_pdf())
            self.assertIn("Synthetic project context.", extract_text_from_file(path))


if __name__ == "__main__":
    unittest.main()
