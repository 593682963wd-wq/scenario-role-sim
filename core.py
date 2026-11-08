"""作者：Wangyuan；日期：2026-10-29；职责：本地情景实验，随机模型分数不代表现实预测概率。"""
from simulation.engine import build_project_analysis,run_prediction_simulation,build_simulation_artifacts

def run(payload):
    if not isinstance(payload,dict):raise TypeError('输入必须为对象')
    question=payload.get('question','');material=payload.get('material','')
    if not isinstance(question,str) or not isinstance(material,str):raise TypeError('question/material必须为文本')
    project=build_project_analysis(title='合成情景实验',question=question,material_name='caller-text',material_path='',material_text=material,agent_count=4,seed=7)
    result,report=run_prediction_simulation(project,agent_count=4,rounds=payload.get('rounds',3),seed=7,llm_enabled=False)
    return {'project':project.to_dict(),'simulation':result.to_dict(),'report':report.to_dict(),'artifacts':build_simulation_artifacts(result),'notice':'启发式模拟，不是可靠概率预测或决策建议。'}
