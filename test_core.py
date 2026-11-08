import unittest,tempfile,json
from pathlib import Path
from core import run

class Tests(unittest.TestCase):
 def test_simulate(self):
  r=run(json.loads(Path('example.json').read_text()));self.assertEqual(len(r['simulation']['events']),12)
  self.assertFalse(r['simulation']['metrics']['llm_enabled'])
 def test_empty(self):
  with self.assertRaises(ValueError):run({})
 def test_invalid(self):
  with self.assertRaises(TypeError):run({'question':7})
 def test_seed(self):
  p=json.loads(Path('example.json').read_text());self.assertEqual(run(p)['simulation']['metrics'],run(p)['simulation']['metrics'])

if __name__=="__main__":unittest.main()
