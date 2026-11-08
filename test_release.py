"""作者：Wangyuan；日期：2026-11-08。职责：通过合成输入复验已确认缺陷。"""
import unittest,tempfile
from pathlib import Path
from dataclasses import replace
from simulation.engine import build_project_analysis,run_prediction_simulation,build_simulation_artifacts,build_simulation_blueprint
from simulation.storage import PredictionStorage
class ReleaseTests(unittest.TestCase):
 def project(self):return build_project_analysis(title='synthetic',question='sample question?',material_name='sample',material_path='',material_text='Sample material about fictional resources and constraints.',seed=1)
 def test_agent_metrics_agree_and_platform_stable(self) -> None:
  p=self.project();run,_=run_prediction_simulation(p,agent_count=12,rounds=1,seed=1)
  self.assertEqual(run.metrics['agent_count'],8);self.assertEqual(len(run.events),8)
  run,_=run_prediction_simulation(p,agent_count=3,rounds=2,seed=1);posts=build_simulation_artifacts(run)['posts']
  for ident in {x['agent_id'] for x in posts}:self.assertEqual(len({x['platform'] for x in posts if x['agent_id']==ident}),1)
 def test_blueprint_duration_agrees_with_bounded_rounds(self) -> None:
  r=build_simulation_blueprint(self.project(),simulation_id="sample",rounds=80)
  self.assertEqual(r['config']['time_config']['total_rounds'],40);self.assertEqual(r['config']['time_config']['total_simulation_hours'],20)
 def test_report_path_cannot_escape(self) -> None:
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);out=root/'outside.md';out.write_text('untouched');s=PredictionStorage(root/'data');_,report=run_prediction_simulation(self.project(),rounds=1)
   with self.assertRaises(ValueError):s.save_report(replace(report,id='../../outside'))
   self.assertEqual(out.read_text(),'untouched')
 def test_graph_lookup_includes_older_than_two_hundred(self) -> None:
  with tempfile.TemporaryDirectory() as d:
   s=PredictionStorage(d);p=self.project()
   for i in range(201):s.save_project(replace(p,id=str(i),graph={'graph_id':str(i)},created_at=f'{i:05d}'))
   self.assertEqual(s.find_project_by_graph_id('0').id,'0')
