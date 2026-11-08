"""作者：Wangyuan；日期：2026-10-29。职责：验证可选PDF辅助函数的合成文字提取。"""
import tempfile
import unittest
from pathlib import Path
from simulation.text_processing import extract_text_from_file

class PdfOptionalTest(unittest.TestCase):
    def test_synthetic_text_layer(self):
        try:import fitz
        except ImportError:self.skipTest('未安装可选requirements-pdf.txt')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'synthetic.pdf'
            with fitz.open() as doc:
                page=doc.new_page();page.insert_text((72,72),'Synthetic project context.');doc.save(path)
            self.assertIn('Synthetic project context.',extract_text_from_file(path))

if __name__=='__main__':unittest.main()
