from __future__ import annotations

import math
import random
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from .llm import call_model_chat
from .models import AgentProfile, PredictionReport, Project, SimulationEvent, SimulationRun
from .text_processing import compact_summary, extract_entities, extract_factors


ROLE_TEMPLATES = [
    ("风险审查者", "优先寻找脆弱点和反例", -0.35),
    ("乐观推动者", "关注机会、增长和正反馈", 0.38),
    ("资源协调者", "判断资源约束和执行节奏", -0.08),
    ("数据分析师", "把高频信号转成概率判断", 0.05),
    ("一线执行者", "关注落地阻力和细节成本", -0.18),
    ("外部公众", "模拟舆论和需求侧反应", 0.12),
    ("决策者", "在收益与风险之间做折中", 0.0),
    ("保守观察者", "等待更多证据再改变立场", -0.22),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def build_project_analysis(
    *,
    title: str,
    question: str,
    material_name: str,
    material_path: str,
    material_text: str,
    agent_count: int = 8,
    seed: int | None = None,
) -> Project:
    if not question.strip():
        raise ValueError("请填写预测问题")
    if not material_text.strip():
        raise ValueError("材料内容为空，无法创建预测项目")
    now = utc_now()
    summary = compact_summary(material_text, question)
    entities = extract_entities(material_text, question)
    factors = extract_factors(material_text, question)
    agents = generate_agents(entities, factors, count=agent_count, seed=seed).copy()
    ontology = build_ontology(entities, factors)
    graph = build_local_graph(entities, factors, material_text)
    environment = build_environment_config(agents, factors)
    clean_title = title.strip() or question.strip()[:30] or "未命名预测项目"
    return Project(
        id=new_id("prj"),
        title=clean_title,
        question=question.strip(),
        material_name=material_name,
        material_path=material_path,
        material_text=material_text,
        summary=summary,
        ontology=ontology,
        graph=graph,
        environment=environment,
        entities=entities,
        factors=factors,
        agents=[agent.to_dict() for agent in agents],
        status="ready",
        created_at=now,
        updated_at=now,
    )


def build_ontology(entities: list[dict[str, Any]], factors: list[dict[str, Any]]) -> dict[str, Any]:
    entity_types = []
    seen_types: set[str] = set()
    for entity in entities:
        entity_type = str(entity.get("type") or "概念")
        if entity_type in seen_types:
            continue
        seen_types.add(entity_type)
        entity_types.append(
            {
                "name": entity_type,
                "description": f"材料中识别出的{entity_type}类节点",
                "attributes": ["name", "weight", "evidence"],
            }
        )
    if not entity_types:
        entity_types.append({"name": "概念", "description": "材料中识别出的概念节点", "attributes": ["name"]})

    edge_types = [
        {
            "name": "影响",
            "description": "因素或主体对预测目标产生正向或负向影响",
            "source": "因素",
            "target": "预测目标",
        },
        {
            "name": "关联",
            "description": "材料中共同出现或语义相关的实体关系",
            "source": "实体",
            "target": "实体",
        },
    ]
    factor_names = [str(item.get("name")) for item in factors[:6]]
    return {
        "entity_types": entity_types,
        "edge_types": edge_types,
        "analysis_summary": f"本地生成 {len(entity_types)} 类实体、{len(edge_types)} 类关系；核心因素：{'、'.join(factor_names) or '整体走势'}。",
    }


def build_local_graph(
    entities: list[dict[str, Any]],
    factors: list[dict[str, Any]],
    material_text: str,
) -> dict[str, Any]:
    nodes = []
    for idx, entity in enumerate(entities, start=1):
        nodes.append(
            {
                "id": f"node_{idx:02d}",
                "label": entity.get("name"),
                "type": entity.get("type"),
                "weight": entity.get("weight", 0.4),
            }
        )
    offset = len(nodes)
    for idx, factor in enumerate(factors[:8], start=1):
        nodes.append(
            {
                "id": f"factor_{idx:02d}",
                "label": factor.get("name"),
                "type": "因素",
                "weight": factor.get("score", 0.5),
            }
        )

    edges = []
    for idx, factor in enumerate(factors[:8], start=1):
        if not nodes:
            break
        target = nodes[(idx - 1) % max(1, offset or len(nodes))]["id"]
        edges.append(
            {
                "id": f"edge_{idx:02d}",
                "source": f"factor_{idx:02d}",
                "target": target,
                "type": "影响",
                "direction": factor.get("direction", "neutral"),
            }
        )
    chunk_count = max(1, len(material_text) // 500 + (1 if len(material_text) % 500 else 0))
    return {
        "graph_id": new_id("local_graph"),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "chunk_count": chunk_count,
        "nodes": nodes[:30],
        "edges": edges[:30],
        "note": "本地轻量图谱；未接 Zep Cloud 时用于替代原项目的 Standalone Graph。",
    }


def build_environment_config(agents: list[AgentProfile], factors: list[dict[str, Any]]) -> dict[str, Any]:
    twitter_profiles = []
    reddit_profiles = []
    for agent in agents:
        profile = {
            "id": agent.id,
            "name": agent.name,
            "role": agent.role,
            "stance": agent.stance,
            "focus": agent.focus,
        }
        if len(twitter_profiles) <= len(reddit_profiles):
            twitter_profiles.append(profile)
        else:
            reddit_profiles.append(profile)
    return {
        "platforms": ["twitter-like", "reddit-like"],
        "twitter_profiles": twitter_profiles,
        "reddit_profiles": reddit_profiles,
        "simulation_config": {
            "default_rounds": 6,
            "actions": ["发帖", "评论", "转发", "支持", "反对", "观望"],
            "focus_factors": [str(item.get("name")) for item in factors[:6]],
        },
        "note": "本地环境配置模拟原项目的 OASIS profile/config 生成步骤。",
    }


def build_simulation_blueprint(
    project: Project,
    *,
    simulation_id: str,
    agent_count: int = 8,
    rounds: int = 6,
    seed: int | None = None,
    llm_enabled: bool = False,
    llm_config: dict[str, str] | None = None,
) -> dict[str, Any]:
    seed_value = seed if seed is not None else stable_seed(project.id + project.question)
    agents = generate_agents(project.entities, project.factors, count=agent_count, seed=seed_value)
    twitter_profiles, reddit_profiles = split_platform_profiles(agents)
    config = build_oasis_like_config(project, rounds=rounds, profiles=agents)
    model_note = None
    if llm_enabled:
        model_note = build_model_environment_note(project, llm_config or {})
    return {
        "simulation_id": simulation_id,
        "project_id": project.id,
        "graph_id": project.graph.get("graph_id"),
        "status": "prepared",
        "phase": "environment_ready",
        "profiles": {
            "twitter": twitter_profiles,
            "reddit": reddit_profiles,
            "all": twitter_profiles + reddit_profiles,
        },
        "config": config,
        "model_note": model_note,
        "current_round": 0,
        "total_rounds": int(config["time_config"]["total_rounds"]),
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }


def split_platform_profiles(agents: list[AgentProfile]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    twitter_profiles: list[dict[str, Any]] = []
    reddit_profiles: list[dict[str, Any]] = []
    for idx, agent in enumerate(agents, start=1):
        profile = {
            "agent_id": agent.id,
            "name": agent.name,
            "username": f"{agent.role.lower().replace(' ', '_')}_{idx:02d}",
            "profession": agent.role,
            "bio": agent.memory,
            "personality": agent.stance,
            "stance": agent.stance,
            "focus": agent.focus,
            "bias": agent.bias,
            "platform": "twitter" if idx % 2 else "reddit",
        }
        if idx % 2:
            twitter_profiles.append(profile)
        else:
            reddit_profiles.append(profile)
    return twitter_profiles, reddit_profiles


def build_oasis_like_config(
    project: Project,
    *,
    rounds: int,
    profiles: list[AgentProfile],
) -> dict[str, Any]:
    factors = [str(item.get("name")) for item in project.factors[:8] if item.get("name")]
    return {
        "name": f"{project.title} 双平台仿真",
        "simulation_requirement": project.question,
        "platforms": ["twitter", "reddit"],
        "time_config": {
            "total_rounds": max(1, min(40, int(rounds or 6))),
            "minutes_per_round": 30,
            "total_simulation_hours": round(max(1,min(40,int(rounds or 6))) * 0.5, 1),
        },
        "agent_config": {
            "agent_count": len(profiles),
            "profile_source": "local_rules",
            "memory_source": "local_graph",
        },
        "action_space": ["post", "comment", "repost", "like", "support", "oppose", "watch"],
        "topic_config": {
            "primary_topic": project.question,
            "focus_factors": factors or ["整体走势"],
            "seed_material": project.material_name,
        },
        "graph_memory_update": {
            "enabled": True,
            "mode": "local_append_only",
        },
    }


def build_model_environment_note(project: Project, llm_config: dict[str, str]) -> str:
    try:
        return call_model_chat(
            provider=llm_config.get("provider", "ollama"),
            base_url=llm_config.get("base_url", ""),
            api_key=llm_config.get("api_key", ""),
            model=llm_config.get("model", ""),
            timeout=90,
            messages=[
                {
                    "role": "system",
                    "content": "你是多智能体仿真配置助手。用中文写一段不超过120字的环境设定，不要虚构具体数据。",
                },
                {
                    "role": "user",
                    "content": f"预测问题：{project.question}\n材料摘要：{project.summary.get('brief', '')}",
                },
            ],
        )
    except Exception as exc:
        return f"本地模型增强未成功：{exc}"


def generate_agents(
    entities: list[dict[str, Any]],
    factors: list[dict[str, Any]],
    *,
    count: int,
    seed: int | None = None,
) -> list[AgentProfile]:
    count = max(3, min(len(ROLE_TEMPLATES), int(count or 8)))
    rng = random.Random(seed if seed is not None else 20260610)
    focus_pool = [str(item.get("name")) for item in factors if item.get("name")]
    if not focus_pool:
        focus_pool = [str(item.get("name")) for item in entities if item.get("name")]
    if not focus_pool:
        focus_pool = ["整体走势"]

    agents: list[AgentProfile] = []
    for idx, (role, stance, bias) in enumerate(ROLE_TEMPLATES[:count], start=1):
        focus = focus_pool[(idx - 1) % len(focus_pool)]
        wobble = rng.uniform(-0.07, 0.07)
        agents.append(
            AgentProfile(
                id=f"agent_{idx:02d}",
                name=f"{role}{idx}",
                role=role,
                stance=stance,
                memory=f"长期关注 {focus}，会把材料里的局部信号带入判断。",
                bias=round(bias + wobble, 3),
                focus=focus,
            )
        )
    return agents


def run_prediction_simulation(
    project: Project,
    *,
    agent_count: int = 8,
    rounds: int = 6,
    seed: int | None = None,
    llm_enabled: bool = False,
    llm_config: dict[str, str] | None = None,
) -> tuple[SimulationRun, PredictionReport]:
    rounds = max(1, min(40, int(rounds or 6)))
    agent_count = max(3, min(len(ROLE_TEMPLATES), int(agent_count or 8)))
    seed_value = seed if seed is not None else stable_seed(project.question + project.material_name)
    rng = random.Random(seed_value)

    agents = generate_agents(project.entities, project.factors, count=agent_count, seed=seed_value)
    factors = project.factors or [{"name": "整体走势", "score": 0.5, "direction": "neutral", "evidence": ""}]

    events: list[SimulationEvent] = []
    momentum = 0.0
    risk = 0.0
    disagreement = 0.0
    for round_no in range(1, rounds + 1):
        round_deltas: list[float] = []
        for agent in agents:
            factor = rng.choice(factors)
            factor_score = float(factor.get("score") or 0.5)
            direction = str(factor.get("direction") or "neutral")
            directional_push = (factor_score - 0.5) * 0.36
            if direction == "risk":
                directional_push -= 0.09
                risk += 0.025 + factor_score * 0.018
            elif direction == "opportunity":
                directional_push += 0.07
            delta = agent.bias * 0.45 + directional_push + rng.uniform(-0.08, 0.08)
            delta = max(-0.42, min(0.42, delta))
            round_deltas.append(delta)
            momentum += delta / max(1, agent_count)
            note = build_event_note(agent, factor, delta, round_no)
            events.append(
                SimulationEvent(
                    round=round_no,
                    agent_id=agent.id,
                    agent_name=agent.name,
                    focus=agent.focus,
                    signal=str(factor.get("name") or "整体走势"),
                    stance=agent.stance,
                    delta=round(delta, 3),
                    note=note,
                )
            )
        if round_deltas:
            mean_delta = sum(round_deltas) / len(round_deltas)
            variance = sum((item - mean_delta) ** 2 for item in round_deltas) / len(round_deltas)
            disagreement += math.sqrt(variance)

    base_probability = 0.5 + math.tanh(momentum / max(1, rounds)) * 0.28 - min(risk, 0.35) * 0.25
    probability = round(max(0.08, min(0.92, base_probability)), 2)
    metrics = {
        "probability": probability,
        "risk_index": round(max(0.0, min(1.0, risk)), 2),
        "disagreement_index": round(max(0.0, min(1.0, disagreement / max(1, rounds))), 2),
        "rounds": rounds,
        "agent_count": agent_count,
        "seed": seed_value,
        "llm_enabled": bool(llm_enabled),
        "platforms": project.environment.get("platforms", ["local"]),
    }
    now = utc_now()
    run = SimulationRun(
        id=new_id("run"),
        project_id=project.id,
        status="completed",
        params={
            "agent_count": agent_count,
            "rounds": rounds,
            "seed": seed_value,
            "llm_enabled": bool(llm_enabled),
        },
        events=[event.to_dict() for event in events],
        metrics=metrics,
        report_id=None,
        created_at=now,
        completed_at=now,
    )
    report = build_report(project, run, metrics, llm_enabled=llm_enabled, llm_config=llm_config or {})
    run = SimulationRun(
        id=run.id,
        project_id=run.project_id,
        status=run.status,
        params=run.params,
        events=run.events,
        metrics=run.metrics,
        report_id=report.id,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )
    return run, report


def build_simulation_artifacts(run: SimulationRun) -> dict[str, Any]:
    events = run.events
    timeline = build_timeline(events)
    posts = build_platform_posts(events)
    actions = build_actions(events)
    agent_stats = build_agent_stats(events)
    return {
        "timeline": timeline,
        "posts": posts,
        "actions": actions,
        "agent_stats": agent_stats,
    }


def build_timeline(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for event in events:
        grouped.setdefault(int(event.get("round") or 0), []).append(event)
    timeline = []
    for round_no in sorted(grouped):
        items = grouped[round_no]
        avg_delta = sum(float(item.get("delta") or 0) for item in items) / max(1, len(items))
        tone = "support" if avg_delta > 0.04 else "oppose" if avg_delta < -0.04 else "mixed"
        timeline.append(
            {
                "round": round_no,
                "event_count": len(items),
                "avg_delta": round(avg_delta, 3),
                "tone": tone,
                "summary": f"第{round_no}轮出现 {len(items)} 条互动，整体倾向 {tone_text(tone)}。",
            }
        )
    return timeline


def build_platform_posts(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    posts = []
    for idx, event in enumerate(events, start=1):
        agent_number=next(i for i,key in enumerate(dict.fromkeys(x.get("agent_id") for x in events),1) if key==event.get("agent_id"))
        platform = "twitter" if agent_number % 2 else "reddit"
        delta = float(event.get("delta") or 0)
        sentiment = "positive" if delta > 0.03 else "negative" if delta < -0.03 else "neutral"
        action = "转发讨论" if platform == "twitter" and abs(delta) > 0.12 else "长帖分析" if platform == "reddit" else "评论观察"
        posts.append(
            {
                "post_id": f"{platform}_{idx:04d}",
                "platform": platform,
                "round": event.get("round"),
                "agent_id": event.get("agent_id"),
                "author": event.get("agent_name"),
                "topic": event.get("signal"),
                "sentiment": sentiment,
                "action": action,
                "content": event.get("note"),
                "impact": round(delta, 3),
            }
        )
    return posts


def build_actions(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions = []
    for idx, event in enumerate(events, start=1):
        delta = float(event.get("delta") or 0)
        if delta > 0.16:
            action_type = "support"
        elif delta < -0.16:
            action_type = "oppose"
        elif abs(delta) > 0.08:
            action_type = "comment"
        else:
            action_type = "watch"
        actions.append(
            {
                "action_id": f"act_{idx:04d}",
                "round": event.get("round"),
                "agent_id": event.get("agent_id"),
                "agent_name": event.get("agent_name"),
                "type": action_type,
                "target": event.get("signal"),
                "delta": round(delta, 3),
            }
        )
    return actions


def build_agent_stats(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for event in events:
        agent_id = str(event.get("agent_id"))
        item = stats.setdefault(
            agent_id,
            {
                "agent_id": agent_id,
                "agent_name": event.get("agent_name"),
                "event_count": 0,
                "positive": 0,
                "negative": 0,
                "avg_delta": 0.0,
                "focus": event.get("focus"),
            },
        )
        delta = float(event.get("delta") or 0)
        item["event_count"] += 1
        item["positive"] += 1 if delta > 0 else 0
        item["negative"] += 1 if delta < 0 else 0
        item["avg_delta"] += delta
    for item in stats.values():
        item["avg_delta"] = round(item["avg_delta"] / max(1, item["event_count"]), 3)
    return sorted(stats.values(), key=lambda item: item["event_count"], reverse=True)


def tone_text(tone: str) -> str:
    return {"support": "支持增强", "oppose": "反对增强", "mixed": "分歧扩大"}.get(tone, "分歧扩大")


def build_event_note(agent: AgentProfile, factor: dict[str, Any], delta: float, round_no: int) -> str:
    signal = str(factor.get("name") or "整体走势")
    evidence = str(factor.get("evidence") or "").strip()
    direction = "上调" if delta >= 0 else "下调"
    evidence_part = f"；依据：{evidence[:70]}" if evidence else ""
    return f"第{round_no}轮，{agent.role}围绕「{signal}」{direction}判断，幅度 {abs(delta):.2f}{evidence_part}"


def build_report(
    project: Project,
    run: SimulationRun,
    metrics: dict[str, Any],
    *,
    llm_enabled: bool,
    llm_config: dict[str, str],
) -> PredictionReport:
    probability = float(metrics["probability"])
    risk_level = "green" if probability >= 0.62 else "amber" if probability >= 0.38 else "red"
    headline = make_headline(project.question, probability, risk_level)
    key_drivers = select_key_drivers(project.factors, run.events)
    scenarios = build_scenarios(project.question, probability, metrics)
    counter_arguments = build_counter_arguments(project.factors, probability)
    watch_indicators = build_watch_indicators(project.factors, project.entities)
    next_steps = build_next_steps(risk_level)
    llm_note: str | None = None
    if llm_enabled:
        try:
            llm_note = call_model_chat(
                provider=llm_config.get("provider", "ollama"),
                base_url=llm_config.get("base_url", ""),
                api_key=llm_config.get("api_key", ""),
                model=llm_config.get("model", ""),
                timeout=90,
                messages=[
                    {
                        "role": "system",
                        "content": "你是预测报告审稿人。用中文补充一段不超过160字的判断，不要编造具体数据。",
                    },
                    {
                        "role": "user",
                        "content": f"问题：{project.question}\n本地模拟结论：{headline}\n关键因素：{key_drivers}",
                    },
                ],
            )
        except Exception as exc:
            llm_note = f"模型增强未成功：{exc}"

    markdown = render_markdown_report(
        project=project,
        headline=headline,
        probability=probability,
        risk_level=risk_level,
        scenarios=scenarios,
        key_drivers=key_drivers,
        counter_arguments=counter_arguments,
        watch_indicators=watch_indicators,
        next_steps=next_steps,
        llm_note=llm_note,
    )
    now = utc_now()
    return PredictionReport(
        id=new_id("rep"),
        project_id=project.id,
        run_id=run.id,
        headline=headline,
        probability=probability,
        risk_level=risk_level,
        scenarios=scenarios,
        key_drivers=key_drivers,
        counter_arguments=counter_arguments,
        watch_indicators=watch_indicators,
        next_steps=next_steps,
        markdown=markdown,
        created_at=now,
        llm_note=llm_note,
        raw={"metrics": metrics, "summary": project.summary},
    )


def select_key_drivers(factors: list[dict[str, Any]], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    event_counter: dict[str, int] = {}
    for event in events:
        signal = str(event.get("signal") or "")
        event_counter[signal] = event_counter.get(signal, 0) + 1
    ranked = sorted(
        factors,
        key=lambda item: (float(item.get("score") or 0), event_counter.get(str(item.get("name")), 0)),
        reverse=True,
    )
    return ranked[:5]


def build_scenarios(question: str, probability: float, metrics: dict[str, Any]) -> list[dict[str, Any]]:
    risk_index = float(metrics.get("risk_index") or 0)
    return [
        {
            "name": "基准情景",
            "probability": probability,
            "summary": f"按当前材料信号推演，问题「{question}」更可能沿中性偏稳路径发展。",
        },
        {
            "name": "乐观情景",
            "probability": round(min(0.95, probability + 0.16), 2),
            "summary": "如果机会因素连续增强、执行阻力降低，结果会明显好于基准判断。",
        },
        {
            "name": "压力情景",
            "probability": round(max(0.05, probability - 0.18 - risk_index * 0.08), 2),
            "summary": "如果风险因素集中兑现、关键主体反应保守，结果会转向低位或延后。",
        },
    ]


def build_counter_arguments(factors: list[dict[str, Any]], probability: float) -> list[str]:
    risk_factors = [factor for factor in factors if factor.get("direction") == "risk"]
    opportunity_factors = [factor for factor in factors if factor.get("direction") == "opportunity"]
    arguments: list[str] = []
    if probability >= 0.55:
        for factor in risk_factors[:2]:
            arguments.append(f"不能忽视「{factor.get('name')}」：{factor.get('evidence') or '材料中已有风险信号。'}")
        arguments.append("材料可能存在单一来源偏差，真实外部反馈可能比文本更分裂。")
    else:
        for factor in opportunity_factors[:2]:
            arguments.append(f"也存在改善窗口：「{factor.get('name')}」可能带来正反馈。")
        arguments.append("当前低概率判断不等于失败，只表示需要更多条件同时成立。")
    return arguments[:3]


def build_watch_indicators(factors: list[dict[str, Any]], entities: list[dict[str, Any]]) -> list[str]:
    indicators = [f"持续跟踪「{factor.get('name')}」是否出现方向性变化" for factor in factors[:3]]
    indicators.extend([f"观察「{entity.get('name')}」的公开表态或行为变化" for entity in entities[:2]])
    indicators.append("每轮新增材料后复跑模拟，比较概率和风险指数变化")
    return indicators[:6]


def build_next_steps(risk_level: str) -> list[str]:
    if risk_level == "green":
        return ["保留当前方案，补充监测指标", "准备对外/对内说明口径", "在出现新材料时复跑一次模拟"]
    if risk_level == "amber":
        return ["补充反方材料，避免只看单边证据", "把关键风险拆成可观察指标", "用小轮数先做两组对照模拟"]
    return ["暂缓下强结论，先补齐关键材料", "优先验证最高风险因素", "设置触发条件，满足后再进入下一轮推演"]


def make_headline(question: str, probability: float, risk_level: str) -> str:
    level_text = {"green": "偏乐观", "amber": "不确定性较高", "red": "压力偏大"}[risk_level]
    return f"围绕「{question}」，当前模拟判断为{level_text}，基准概率约 {probability:.0%}。"


def render_markdown_report(
    *,
    project: Project,
    headline: str,
    probability: float,
    risk_level: str,
    scenarios: list[dict[str, Any]],
    key_drivers: list[dict[str, Any]],
    counter_arguments: list[str],
    watch_indicators: list[str],
    next_steps: list[str],
    llm_note: str | None,
) -> str:
    lines = [
        f"# {project.title}",
        "",
        f"**结论**：{headline}",
        f"**风险等级**：{risk_level}",
        f"**基准概率**：{probability:.0%}",
        "",
        "## 三种情景",
    ]
    for scenario in scenarios:
        lines.append(f"- {scenario['name']}（{scenario['probability']:.0%}）：{scenario['summary']}")
    lines.extend(["", "## 关键驱动因素"])
    for driver in key_drivers:
        lines.append(f"- {driver.get('name')}：{driver.get('evidence') or '材料中出现该信号。'}")
    lines.extend(["", "## 反对观点"])
    for argument in counter_arguments:
        lines.append(f"- {argument}")
    lines.extend(["", "## 观察指标"])
    for indicator in watch_indicators:
        lines.append(f"- {indicator}")
    lines.extend(["", "## 下一步建议"])
    for step in next_steps:
        lines.append(f"- {step}")
    if llm_note:
        lines.extend(["", "## 模型增强备注", llm_note])
    return "\n".join(lines).strip() + "\n"


def chat_with_report(
    *,
    project: Project,
    report: PredictionReport,
    question: str,
    llm_enabled: bool = False,
    llm_config: dict[str, str] | None = None,
) -> dict[str, Any]:
    clean_question = question.strip()
    if not clean_question:
        raise ValueError("请先输入追问内容")
    local_answer = local_report_answer(project, report, clean_question)
    if not llm_enabled:
        return {"answer": local_answer, "mode": "local"}
    try:
        enhanced = call_model_chat(
            provider=(llm_config or {}).get("provider", "ollama"),
            base_url=(llm_config or {}).get("base_url", ""),
            api_key=(llm_config or {}).get("api_key", ""),
            model=(llm_config or {}).get("model", ""),
            timeout=90,
            messages=[
                {
                    "role": "system",
                    "content": "你是预测报告交互助手。只能基于给定报告和材料摘要回答，中文，先给结论。",
                },
                {
                    "role": "user",
                    "content": (
                        f"材料摘要：{project.summary.get('brief')}\n"
                        f"报告：{report.markdown[:4000]}\n"
                        f"用户追问：{clean_question}"
                    ),
                },
            ],
        )
        return {"answer": enhanced, "mode": "llm"}
    except Exception as exc:
        return {"answer": f"{local_answer}\n\n模型增强未成功：{exc}", "mode": "local_fallback"}


def local_report_answer(project: Project, report: PredictionReport, question: str) -> str:
    q = question.lower()
    if any(word in q for word in ("风险", "反对", "问题", "risk")):
        return "主要风险/反对观点：\n" + "\n".join(f"- {item}" for item in report.counter_arguments)
    if any(word in q for word in ("依据", "为什么", "驱动", "driver")):
        return "当前判断主要依据这些驱动因素：\n" + "\n".join(
            f"- {driver.get('name')}：{driver.get('evidence') or '材料中反复出现'}"
            for driver in report.key_drivers
        )
    if any(word in q for word in ("情景", "概率", "scenario")):
        return "三种情景如下：\n" + "\n".join(
            f"- {scenario['name']}（{scenario['probability']:.0%}）：{scenario['summary']}"
            for scenario in report.scenarios
        )
    if any(word in q for word in ("下一步", "建议", "怎么做")):
        return "建议下一步：\n" + "\n".join(f"- {step}" for step in report.next_steps)
    return (
        f"{report.headline}\n\n"
        f"材料摘要：{project.summary.get('brief', '')[:260]}\n\n"
        "你可以继续问：为什么这么判断、最大风险是什么、下一步怎么做。"
    )


def stable_seed(value: str) -> int:
    total = 0
    for idx, char in enumerate(value[:200], start=1):
        total += idx * ord(char)
    return total % 1_000_000
