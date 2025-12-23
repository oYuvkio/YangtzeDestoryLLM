摘要翻译
该研究旨在通过开发一个强大的洪水本体，以提高洪水风险沟通的效率，特别是针对社会经济脆弱群体。研究提出了一种新的半自动化方法，将人类专家定义的模式与大语言模型（LLM）驱动的扩展相结合。通过构建的洪水本体，研究证明了其能够将复杂数据转化为清晰、个性化的公共警报。通过技术评估，LLM构建的本体在关系丰富性和表达力上优于现有灾难本体。此外，通过实际案例研究展示了该本体如何改进洪水预警信息，变得更具针对性和可操作性。

方法动机
a) 为什么提出该方法？阐述其背后的驱动力。
该方法的提出是为了弥补当前洪水风险沟通中的两个主要缺陷：一是现有的灾难本体过于专业，难以为公众提供具体的、易懂的洪水风险信息；二是现有的本体构建方式主要依赖手动方法，效率低且难以扩展。通过结合人工专家和AI技术，本研究提出了一个可扩展且适用于公共风险沟通的本体构建方法。

b) 现有方法的痛点/不足是什么？具体指出局限性。

现有方法的痛点在于：

许多洪水本体主要为专家设计，缺乏针对公众沟通的细节和易懂性。

本体构建通常依赖手动流程，无法快速适应变化的环境或大规模更新。

全自动化方法，如大语言模型，可能会出现语义漂移或虚假信息生成（幻觉现象），不适用于高风险的实时沟通。

c) 论文的研究假设或直觉是什么？

该研究假设通过半自动化的本体构建方法，可以有效结合人类专家的知识与AI的处理能力，从而提升洪水风险沟通的质量和效率，尤其是在社会经济脆弱群体的灾难响应中。

方法设计
a) 方法流程总结
专家定义初步本体：通过对洪水风险沟通的需求进行分析，结合专家的访谈，确定本体的高层次结构（如洪水类型、洪水阶段、影响因素等），并使用LLM生成标签和描述，建立初步本体 。

基于能力问题的本体扩展：利用LLM生成能力问题（CQs），通过这些问题分析洪水风险沟通中的关键分析挑战，从而驱动本体的扩展。生成的实体和关系经过自动化验证后加入本体中 。

从权威文件扩展本体：通过提取来自FEMA、国家气象局等机构的文件和新闻文章，进一步丰富本体的概念和实例。LLM通过分类提取知识，加入到现有本体中 。

实例填充：从网络抓取洪水相关的新闻文章，将提取的知识实例化并加入本体，形成完整的知识图谱 。

b) 如果涉及模型结构，请描述每个模块的功能与作用

专家定义模块：人类专家负责初步定义本体框架和类别，确保本体的主题广度和深度。

LLM生成模块：LLM在扩展本体时生成概念、关系以及相关的能力问题，能够在没有过多人工干预的情况下快速扩展本体。

验证和精化模块：通过人工和自动化的双重验证，确保LLM生成的实体和关系在语义上的一致性和正确性。

c) 如果有公式/算法，请用通俗语言解释它们的意义

在评估本体的覆盖率时，使用了余弦相似度来评估每个能力问题的概念与本体概念之间的匹配度。公式**RR = P / (P + SC)**计算了本体中关系丰富度（RR），P为非继承关系数量，SC为继承关系数量。较高的RR值表示本体中包含更多的语义关系，适用于复杂的风险沟通 。

与其他方法对比
a) 本方法和现有主流方法相比，有什么本质不同？
本方法的核心创新在于结合人工专家和LLM，避免了传统全自动方法中的语义漂移和幻觉现象。此外，本方法专注于构建面向公众的、易理解的洪水风险沟通本体，而非仅仅为专家提供技术支持。

b) 创新点在哪里？

引入了专家与AI协作的半自动化方法，解决了全自动化方法无法提供高质量本体的局限性。

本体结构专门针对洪水风险沟通，能够转化为具体的、可操作的公共警报 。

c) 在什么场景下更适用？

本方法特别适用于洪水等灾难的风险沟通，尤其是面对社会经济脆弱群体的洪水预警和应急响应场景。

d) 用表格总结 方法对比（优点/缺点/改进点）
方法 优点 缺点 改进点
现有方法 专家驱动，适合专业应用 速度慢，扩展性差，适用面狭窄 增强速度和灵活性，扩大适用范围
本方法 结合AI与专家，提升效率，增强适用性 层次结构较浅，可能缺乏细节深度 增强层次结构，丰富数据属性
4. 实验表现与优势
a) 作者如何验证该方法的有效性？

通过OntoQA评估本体结构的丰富性，并通过案例研究展示本体如何转化洪水警报为可操作的公众警告 。

b) 实验结果在哪些指标上超越了对比方法？

本方法在**关系丰富度（RR）**上显著超过了现有灾难本体，如FDSO和DMDO 。

c) 哪些场景/数据集下优势最明显？

在洪水风险沟通的应用场景中，特别是对社会经济脆弱群体的风险预警，显示出明显优势 。

d) 是否有局限性（比如泛化能力、计算开销、对特定数据的依赖）？

本方法存在层次结构较浅的问题，未来可通过引入更多细粒度数据来增强本体的描述力 。

学习与应用
a) 论文是否开源？
是的，论文中的方法是开源的，用户可以通过获取论文中的代码和模型实现该方法 。

b) 需要注意哪些超参数、数据预处理、训练细节？

关键步骤包括生成能力问题和实体提取，LLM的低温度设置（T=0.1）有助于减少幻觉现象 。

c) 该方法能否迁移到其他任务？

该方法具有较强的迁移性，可以应用于其他灾难管理领域，如火灾、地震等 。

总结
a) 核心思想：
将人类专家与AI结合，构建适用于洪水风险沟通的半自动化本体 。

b) “速记版pipeline”：

专家定义本体初始结构；

使用LLM扩展并生成能力问题；

从权威文件中提取并丰富本体；

用实际数据填充实例并验证 。 以上是我的一篇参考论文。以下是我的方法：我的方法（论文式写法）：CQ 驱动的长江流域水旱灾害本体/知识图谱构建框架（与原论文逐阶段对比）
对标原论文：《洪水本体构建的半自动化框架》（见 txts/survey/water_summary.md）
我的实现仓库：YangtzeDestoryLLM/（核心代码：kg/cq_pipeline.py、kg/prompts.py、kg/llm_core.py、scripts/run_p4_batch.py、tools/tbox_metrics.py 等）

摘要
本文面向“长江流域水旱灾害（洪水/干旱）”的硕士论文需求，构建了一套 CQ（Competency Questions，能力问题）驱动 的半自动化本体（TBox）与知识图谱（ABox）构建流程，用于支撑后续的 KG-RAG 问答系统。方法上借鉴原论文“人机协同 + LLM 扩展 + 多源语料富集”的总体思路，但将“专家先写顶层类/类层级”替换为“以 CQ 作为需求规范 → 反推 TBox”，并在工程实现中引入 JSON 强制输出、断点续跑、支持度聚合（min_support）、同义对齐、向量去重、冲突检测、TBox 约束抽取与结果清洗 等机制以提高可复现性与鲁棒性。最终产出包括：多版本 TBox（P2/P3/P4）、基于 TBox 约束的事件与三元组抽取结果（P5）、以及 OntoQA（RR/IR/AR）与 CQ 覆盖度等评估报告，为答辩/论文写作提供可直接引用的实验材料。

方法动机
a) 我为什么选择参考这篇论文

问题契合：原论文试图解决“灾害领域知识碎片化 → 难以将专业数据转为可理解/可执行信息”的问题；我的系统同样面临“长江流域水旱灾害材料（年鉴/法规/预案/新闻）分散、术语不统一、难以结构化检索与推理”的现实。

方法吸引点：原论文的“半自动化 + 人机协同”给了我一个可落地的工程路线：
● 让 LLM 做“扩展/归纳/抽取”的高吞吐工作；
● 用规则/评估/人工审核兜底，避免纯自动幻觉；
● 以“可复现的流水线”替代零散的人工本体编辑。

对我的直接启发：原论文用 CQ 驱动构建与评估（CQ 覆盖度），这与我“做问答系统”的终端目标天然一致：CQ 本质上就是系统应该能回答的问题集合，可作为需求与评价的共同载体。

b) 我对原论文方法的理解（核心思想、优势、局限）
核心思想（我的复述）：
原论文将本体工程拆成可控的 5 个阶段：

专家定范围与顶层类 → 2) 用 CQ 引导 LLM 扩展 TBox → 3) 用权威文档进一步富集 schema → 4) 用新闻等实例填充 ABox → 5) 用案例验证（把“笼统警报”变成“可执行建议”）。
关键在于：LLM 负责扩展速度，专家审核负责可信度，CQ 负责需求对齐与评估闭环。
优势（原论文）：
● 语义关系更丰富（RR 明显提升），并能服务于“公众风险沟通”的具体下游应用；
● 引入 embedding 去重 + 专家审核，显著降低概念膨胀与语义漂移风险；
● 评估维度较完整：结构指标 + CQ 覆盖 + 案例效果。
局限（原论文）：
● 工具链偏“本体工程”（Protégé/OWL 推理等），对“工程流水线 + 批量语料 + 断点续跑”描述相对少；
● CQ 的筛选与人工审核比例较高（需要专家时间）；
● 与我的目标不同：原论文偏“公众警报生成”，而我偏“KG-RAG 问答/检索/推理”，因此我必须改造其末端验证方式与数据组织方式。
c) 我的改进/调整思路（借鉴/调整/自主设计）
维度 原论文做法 我的做法 怎么不同、为什么
需求规范载体 需求访谈 + 专家定顶层类 领域描述（可由专家/我撰写） + CQ 作为需求规范 我将“顶层类先验”弱化，改为 CQ 反推 schema，便于快速迭代并与问答目标一致
Schema 表达 OWL/Protégé + 公理 JSON TBox（classes/relations/attributes + parent） 以工程可复现为先：JSON 更便于 LLM 强制输出、脚本处理、版本对比；后续可再映射到 OWL/Neo4j
去重与对齐 text-embedding-3-large + 阈值 0.7 + 人审 SentenceTransformer(BGE-base-zh-v1.5, 768 维) + 阈值 0.7 + 自动报告 选择本地 embedding：降低成本、避免 API 限流；保留 review 报告以支持人工抽查
文献增强 文档解析（MunerU）→ LLM 分类提取 JSONL 语料（含上下文/标签）→ P4 批处理 + 支持度聚合 我更强调“批处理可控性”：断点续跑、min_support 过滤、冲突报告，适合长时运行
ABox 填充 新闻抽取实例 + Neo4j TBox 约束下抽取 events/triples（JSON）→ 可选导图/Neo4j 我把“抽取结果”标准化为统一 JSON 结构，便于评测/对比/复用到问答
验证方式 警报优化案例 OntoQA + CQ 覆盖 + 抽取 F1 + QA 对比 下游目标不同：问答系统需要“可检索/可推理/可评测”的指标闭环

方法设计（重点：占全文 60%+）
a) 方法整体框架
原论文框架（回顾）：
阶段1：专家制定初始本体 → 阶段2：CQ驱动的LLM扩展 → 阶段3：权威文档富集 → 阶段4：实例填充 → 阶段5：案例验证
我的框架（落地到代码的“P1P5”）（核心实现：kg/cq_pipeline.py）：
P1：领域范围 → 生成 CQ（能力问题）
P2：CQ → 初始 TBox（classes/relations/attributes + parent）
P3：TBox 规范化（别名归并、层次化、关系清洗、冲突检测；可选向量去重）
P4：语料驱动的 TBox 增强（按文档生成 suggestions → 支持度聚合 → 同义对齐/去重 → 合并；可输出多版本）
P5：TBox 约束下抽取事件与三元组（events + triples），并做最小化结构清洗/一致性校验
框架对比分析（更具体）：
对比维度 原论文 我的方法 差异原因（为什么这么改）
阶段划分 5 个阶段（本体工程语境） 5 个阶段（工程流水线语境：P1P5） 我需要“可跑脚本 + 可复现输出”的阶段边界；每一阶段必须对应清晰的文件产物
初始本体来源 专家先定 6 个顶层类与范围 领域说明文本 → 先产出 CQ，再反推类/关系 我以问答需求为中心：CQ 更贴近“能回答什么问题”，并天然支持后续 CQ 覆盖度评估
文献增强策略 文档分类抽取 + 专家拒绝幻觉 支持度聚合（min_support）+ 冲突检测 + 可选去重 用“多文档重复出现”作为自动置信度信号，减少人工审核工作量，并可在日志/报告中追踪证据来源
实例填充形式 Neo4j 实例填充 + 案例警报生成 JSON events/triples（可再入图）+ QA/抽取评测 我的目标是 KG-RAG：需要标准化抽取结果与可量化评测，不以警报生成作为最终验证
嵌入模型 OpenAI text-embedding-3-large BGE-base-zh-v1.5（768 维，本地推理） 工程与成本约束（离线/低成本），同时保持“余弦相似度阈值 0.7”的论文一致性做法
b) 输入与输出（具体到文件、字段）
原论文（摘要化复述）
● 输入：需求访谈、权威文档（FEMA 等）、网页新闻、NWS 警报案例
● 输出：洪水本体（类/公理/关系）、知识图谱、优化后警报案例
我的方法（代码级别）
输入（按阶段）：
● P1 输入：
○ domain_desc: str（领域范围说明；示例常量：kg/cq_pipeline.py 中 DEMO_DOMAIN_DESC）
● P4 输入：
○ 语料 JSONL（示例：data/corpus_for_onto/p4_only.jsonl，每行是 dict，核心字段：id:str, text:str, context_before:str, context_after:str, filter_labels:dict 等）
● P5 输入：
○ 片段 segment: dict（来自 JSONL），经 build_extraction_input() 拼接上下文后得到 input_text: str
输出（按阶段的“可复现产物”）（典型路径：outputs/cq_pipeline/）：
● P1 输出：p1_cqs*.json
○ 结构：{"cqs": [{"id": str, "question": str, "category": str}, ...]}
● P2/P3/P4 输出：p2_tbox*.json / p3_tbox*.json / p4_tbox*.json
○ 结构：{"classes": [...], "relations": [...], "attributes": [...]}
○ classes[i]：{name:str, cn_name:str, definition:str, examples:list[str], parent:str|None}
○ relations[i]：{name:str, cn_name:str, domain:str, range:str, definition:str, functional:bool}
○ attributes[i]：{owner:str, name:str, cn_name:str, value_type:("string"|"number"|...)}
● P4 中间产物：
○ p4_suggestions.jsonl（逐文档建议，可断点续跑）
○ p4_corpus_suggestions_agg.json（聚合后的建议，含 _support、support_sources）
● P5 输出：p5.json
○ 结构：{"events": list[dict], "triples": list[dict]}
○ 其中 triples[i] 额外可能含 _invalid_predicate: bool（用于标记不符合 TBox 的谓词）
● 评估输出：
○ OntoQA：outputs/ontoqa/metrics.csv|md|json（见 tools/ontoqa_metrics.py/tools/tbox_metrics.py）
○ CQ 覆盖：tools/cq_coverage.py 输出的阈值覆盖率结果

c) 各阶段详细设计（逐一对比 + 代码 + 数据流）
说明：我将“阶段”写作成论文方法章节的颗粒度，但每个阶段都能在代码中找到明确落点（函数/文件/输出文件）。

阶段 1：领域范围界定与 CQ 生成（P1）
原论文做法
● 方法描述：通过需求分析与访谈，专家确定顶层类与范围；LLM 可辅助生成标签/描述。
● 技术细节：LLM 生成 CQ，人工筛选高质量 CQ，并划分扩展/测试集。
我的做法
方法描述（更细）：

写领域范围说明：用结构化要点描述灾害类型、阶段、致灾因子、影响、脆弱性、措施、典型事件等（示例：kg/cq_pipeline.py 中 DEMO_DOMAIN_DESC）。

Prompt 注入“角色 + 约束 + JSON 输出格式”：使用 kg/prompts.py 的 P1_CQ_PROMPT，在 Prompt 中明确：
○ CQ 必须可被结构化查询回答（面向 KG）；
○ 分类（category）集合与覆盖要求；
○ 输出必须是合法 JSON，且仅输出 JSON。

调用 LLM 并强制 JSON：kg/cq_pipeline.py 中 LLMJsonClient.call() 将消息组装为 messages: list[dict] 并调用 llm.chat_messages(..., json_mode=True)。

鲁棒 JSON 解析：若模型输出被 ```json 代码块包裹，先去 fence；若仍无法解析，尝试正则截取 {...}/[...] 片段兜底。

后处理与落盘：过滤掉缺少 question 的条目，构造 List[CQ]，并保存为 p1_cqs*.json。
与原论文的关系：
● 借鉴：使用 CQ 作为需求载体，并强调“可结构化查询回答”。
● 调整：我不先固定“6 个顶层类”，而是用 CQ 反推类/关系；原因是我的系统要做 KG-RAG 问答，CQ 更贴近终端需求，且迭代成本更低。
● 自主设计：LLMJsonClient 的强制 JSON + 兜底解析（工程鲁棒性），让长时批处理更稳定。
关键代码（附逐行中文注释）
代码位置：kg/cq_pipeline.py（类：LLMJsonClient、方法：generate_cqs）
class LLMJsonClient:
"""封装 JSON 强制输出的调用逻辑，屏蔽不同 provider 细节。"""

def call(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
# 1) 按 OpenAI Chat 格式构造 messages（列表，每个元素是 role+content 的 dict）
messages = [
{"role": "system", "content": system_prompt}, # 系统指令：强调“只输出 JSON”
{"role": "user", "content": user_prompt}, # 用户指令：P1_CQ_PROMPT 格式化后的长文本
]
# 2) 调用底层 LLM：json_mode=True 时底层会尝试 response_format=json_object
raw = self.llm.chat_messages(messages, json_mode=True)
# 3) 将 raw 文本做 fence 清理、截取兜底、json.loads，最终返回 dict
return self._safe_load(raw)

def generate_cqs(self, domain_desc: str, n_cq: int = 30, save_path: Optional[Path] = None) -> List[CQ]:
# 1) 将领域说明 domain_desc 与目标数量 n_cq 注入到 Prompt 模板中
user_prompt = P1_CQ_PROMPT.format(domain_desc=domain_desc, n_cq=n_cq)
# 2) 发起 LLM 调用：system_prompt 用极短强约束，user_prompt 承载结构化规范
res = self.client.call("只输出 JSON，字段按提示填写。", user_prompt)
# 3) 从返回 dict 中取出 cqs 数组（类型：list[dict]）
raw_cqs = res.get("cqs", []) or []
cqs: List[CQ] = []
# 4) 遍历并做最小校验：缺 question 直接丢弃；id 缺失则用序号兜底
for i, item in enumerate(raw_cqs, start=1):
q = item.get("question")
if not q:
continue
cqs.append(
CQ(
id=str(item.get("id", i)), # 统一转为 str，避免 int/str 混用
question=q, # 关键字段：能力问题文本
category=item.get("category", ""), # 分类：用于覆盖面分析与后续报告
)
)
# 5) 可选落盘：输出结构 {"cqs": [asdict(CQ), ...]}
if save_path:
self._dump_json({"cqs": [asdict(cq) for cq in cqs]}, save_path)
return cqs
数据流转（变量类型、结构、维度变化）
domain_desc: str
▼ (format)
user_prompt: str
▼ (messages 组装)
messages: list[dict[str, str]] # 长度=2；每个 dict 包含 role/content
▼ (LLM 调用)
raw: str # 可能是纯 JSON，也可能被 json ... 包裹
▼ (strip fence + json.loads + 截取兜底)
res: dict[str, Any] # 期望包含键 "cqs"
▼ (遍历过滤)
cqs: list[CQ] # CQ 是 dataclass：{id:str, question:str, category:str}
▼ (序列化)
p1_cqs*.json # {"cqs": list[dict]}

阶段 2：CQ 反推初始 TBox + 规范化与去重（P2 + P3）
原论文做法
● 方法描述：以 CQ 为驱动，LLM 提取新类/关系；embedding 去重（阈值 0.7）后再人工审核；LLM 提议新类层级位置与语义关系，专家最终定稿。
● 技术细节：模型温度较低（0.1）以保证稳定；去重使用 text-embedding-3-large；逻辑一致性由专家/推理器保障。
我的做法
方法描述（拆解到可实现步骤）：

P2：CQ → 初始模式（TBox）
○ 输入：cqs: list[CQ]
○ 将 CQ 列表序列化为 cq_json: str 注入 P2_SCHEMA_PROMPT；
○ LLM 输出 JSON：classes/relations/attributes 三块；
○ 解析为 dataclass：TBoxSchema(classes, relations, attributes)（见 kg/cq_pipeline.py）。
P3：模式整理（alias 归并 + 关系清洗 + 层次化）
○ 将 P2 的 TBox JSON 注入 P3_REFINEMENT_PROMPT；
○ 得到 p3_result: dict，包含：
■ merged_class_aliases: 别名归并映射（canonical + aliases）
■ relations: 清洗后的关系列表
■ class_hierarchy: 类层级建议（可选，用于解释/报告）
○ 调用 normalize_tbox_with_p3()：把 P2 TBox 映射到 canonical 类名空间，并过滤掉指向不存在类的关系/属性。
可选：向量去重（P2/P3 后均可）
○ 用 EmbeddingDeduplicator 对 classes/relations 做去重；
○ embedding 模型：BAAI/bge-base-zh-v1.5（768 维）；相似度：余弦（通过 normalize_embeddings=True 后点积即余弦）；阈值：默认 0.7（与论文一致）。
冲突检测
○ 对 P3/P4 后 TBox 调用 kg/utils/conflict_detection.py:detect_schema_conflicts()，识别悬空 domain/range/owner、重复定义、孤立类、空定义等，为人工抽查提供“问题清单”。
与原论文的关系：
● 借鉴：CQ 驱动 + 低温度 + embedding 去重（阈值 0.7）。
● 调整：我把“专家审核”部分尽量工程化为“冲突检测 + 去重报告 + review.csv”，原因是硕士阶段人力有限，需要先让流程跑通，再做抽查式人工审核。
● 自主设计：
○ 用 JSON 作为 TBox 中间表示，并提供 _parse_tbox() 的字段过滤，降低模型输出多余字段导致的解析失败。
○ 在 P2/P3 的类定义中加入 parent 字段（继承关系），用于 OntoQA 的 IR 指标计算与后续层级推理（见 ClassDef.parent）。
关键代码（1）：TBox 数据结构与解析（附逐行注释）
代码位置：kg/cq_pipeline.py（dataclass：ClassDef/RelationDef/AttributeDef/TBoxSchema，函数：_parse_tbox）
@dataclass
class ClassDef:
name: str # 英文类名（全局唯一标识）
cn_name: str # 中文类名（便于人工理解与 embedding 表达）
definition: str # 类定义（用于语义区分/去重/覆盖度评估）
examples: List[str] # 示例实例（用于提示与人工审核）
parent: Optional[str] = None # 父类名称（继承边），用于 IR 与层级结构表达
@dataclass
class TBoxSchema:
classes: List[ClassDef]
relations: List[RelationDef]
attributes: List[AttributeDef]

text

def to_dict(self) -> Dict[str, Any]:
    # dataclass -> 可 JSON 序列化 dict；下游脚本统一读写该结构
    return {
        "classes": [asdict(c) for c in self.classes],
        "relations": [asdict(r) for r in self.relations],
        "attributes": [asdict(a) for a in self.attributes],
    }
@staticmethod
def _parse_tbox(data: Dict[str, Any]) -> TBoxSchema:
# 1) pick：仅保留允许字段，避免模型输出多余键导致 dataclass(**dict) 失败
def pick(d: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
return {k: d.get(k) for k in keys if k in d}

text

class_keys = ["name", "cn_name", "definition", "examples", "parent"]
rel_keys   = ["name", "cn_name", "domain", "range", "definition", "functional"]
attr_keys  = ["owner", "name", "cn_name", "value_type"]

# 2) 过滤：类必须至少有 name 和 cn_name；关系必须有 name/domain/range；属性必须有 owner/name
classes = [
    ClassDef(**pick(c, class_keys))
    for c in data.get("classes", []) or []
    if c.get("name") and c.get("cn_name")
]
relations = [
    RelationDef(**pick(r, rel_keys))
    for r in data.get("relations", []) or []
    if r.get("name") and r.get("domain") and r.get("range")
]
attributes = [
    AttributeDef(**pick(a, attr_keys))
    for a in data.get("attributes", []) or []
    if a.get("owner") and a.get("name")
]
return TBoxSchema(classes=classes, relations=relations, attributes=attributes)
关键代码（2）：向量去重（BGE 768 维）与“阈值 0.7”的工程实现
代码位置：kg/utils/deduplication.py
class EmbeddingDeduplicator:
def init(self, model_name: str = "BAAI/bge-base-zh-v1.5", threshold: float = 0.75, device: str = "cpu"):
# 1) 加载 SentenceTransformer（本地模型），默认输出 embedding 维度=768（见模型配置）
self.model = SentenceTransformer(model_name, device=device)
# 2) threshold 即“相似度阈值”，论文对齐推荐 0.7（configs/cfg.yaml 中已统一）
self.threshold = threshold

text

def _encode_texts(self, texts: List[str]):
    # 3) normalize_embeddings=True：将每个向量做 L2 归一化
    #    这样后续点积 np.dot(u, v) 就等价于余弦相似度 cos(u, v)
    return self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

def deduplicate_classes(self, existing_classes: List[dict], candidate_classes: List[dict]) -> DeduplicationResult:
    # 4) 将类表示成“中文名: 定义”的文本，增强语义可区分性
    existing_texts = [f"{c.get('cn_name','')}: {c.get('definition','')}" for c in existing_classes]
    # 5) existing_embs: np.ndarray，形状 (N, 768)；N=已有类数量
    existing_embs = self._encode_texts(existing_texts) if existing_texts else None

    for cand in candidate_classes:
        # 6) cand_emb: np.ndarray，形状 (768,)
        cand_text = f"{cand.get('cn_name','')}: {cand.get('definition','')}"
        cand_emb = self._encode_texts([cand_text])[0]

        # 7) 首个元素直接接纳，用 expand_dims 形成 (1, 768) 的矩阵
        if existing_embs is None:
            accepted.append(cand)
            existing_embs = np.expand_dims(cand_emb, axis=0)
            continue

        # 8) sims: np.ndarray，形状 (N,)；每个值是 cand 与某个 existing 的余弦相似度
        sims = np.dot(existing_embs, cand_emb)
        max_idx = int(sims.argmax())
        max_sim = float(sims[max_idx])

        # 9) 只要 max_sim >= threshold，就判为重复/同义，进入 rejected，并记录“相似于谁/相似度多少”
        if max_sim >= self.threshold:
            rejected.append({**cand, "_rejected_reason": "duplicate", "_similar_to": canonical, "_similarity": max_sim})
        else:
            # 10) 否则接纳，并把 cand_emb 拼到 existing_embs 末尾：形状 (N+1, 768)
            accepted.append(cand)
            existing_embs = np.vstack([existing_embs, cand_emb])
数据流转（从 CQ 到 TBox）
cqs: list[CQ]
▼ (asdict + json.dumps)
cq_json: str
▼ (Prompt format)
user_prompt: str
▼ (LLM JSON 输出)
res: dict[str, Any] with keys {"classes","relations","attributes"}
▼ (_parse_tbox)
tbox_init: TBoxSchema

classes: list[ClassDef] # 每个 ClassDef 至少含 name/cn_name/definition/examples/parent?
relations: list[RelationDef] # 每个 RelationDef 含 name/domain/range/definition/functional
attributes: list[AttributeDef] # 每个 AttributeDef 含 owner/name/cn_name/value_type
▼ (P3 refine + normalize)
tbox_norm: TBoxSchema # canonical 类名空间 + 关系/属性过滤
▼ (optional: dedup)
tbox_dedup: TBoxSchema
与原论文更具体的差异点（怎么不同、为什么）
“继承关系 IR”是我工程里必须显式建模的字段：
原论文在 OWL 中天然有层级（subClassOf），而我早期 JSON TBox 缺 parent 导致 IR=0。为对齐论文评估，我在 ClassDef 中加入 parent 并贯穿 P2/P4 合并逻辑（见 apply_p4_suggestions 支持补 parent）。
去重 embedding 的来源不同：
原论文：OpenAI embedding；我：本地 BGE（768 维）。
怎么不同：模型不同、维度不同，但“归一化 + 点积=余弦 + 阈值 0.7”的判定逻辑一致。
为什么：工程成本/限流约束；且中文灾害文本用中文向量模型更贴近语料语言。
阶段 3：语料驱动的 TBox 增强（P4，批处理 + 支持度聚合 + 去重/对齐/冲突）
原论文做法
● 方法描述：收集权威文档与新闻；PDF 用 MunerU 转文本；LLM 分类提取概念/实例并整合入本体；专家审核并拒绝部分幻觉/歧义候选。
● 技术细节：强调“权威来源”；统计被拒比例（实体约 8%，关系约 10%）。
我的做法
方法描述（两条线：单文档 P4 与批处理 P4）：
(A) 单文档 P4（核心函数，便于解释 Prompt → suggestions）

输入：
○ schema: TBoxSchema（来自 P3）
○ doc_text: str（一段文献/制度/年鉴/新闻文本）
Prompt：kg/prompts.py:P4_AUGMENT_PROMPT
○ 要求输出 suggestions: list[dict]；
○ 每条 suggestion 必须包含：
type/name/cn_name/definition/parent_or_domain_range_or_owner/value_type/evidence
输出：p4_result: dict（仅建议，不直接改 TBox）
(B) 批处理 P4（我的工程重点：可扩展、可复现、可断点续跑）
对应脚本：scripts/run_p4_batch.py（被 run_p3_p4_with_hierarchy.sh 调用）
语料读取：从 data/corpus_for_onto/p4_only.jsonl 读取文档列表 jsonl_docs: list[dict]。
断点续跑：若存在 p4_suggestions.jsonl 且未指定 --overwrite：
○ 先把已生成的 suggestion 全部读入 raw_suggestions: list[dict]；
○ 提取 processed_doc_ids: set[str]，后续只处理未跑过的 doc_id。
逐文档调用 LLM：对每条 doc：
○ 取 doc_text = doc["text"]（必要时截断/清洗）；
○ 调 pipeline.enhance_schema(base_tbox, doc_text) 得到 suggestions；
○ 为每条 suggestion 增加审计字段：doc_id/_source/evidence_span/... 并 append 写入 JSONL。
聚合与频次统计（核心“自动置信度”机制）：
○ 用 key 聚合：(type, name, parent_or_domain_range_or_owner, range)；
○ 给每条聚合项添加：
■ _support: int（出现次数）
■ _support_sources: list[str]（出现过的 doc_id 列表，便于追溯证据）
过滤 + 合并（生成多版本 TBox）：
○ min_support：只合并 _support >= min_support 的建议（默认 2）；
○ allow_new_classes：是否允许新增类（allow0/allow1 两种策略）；
○ align_names：同义对齐（kg/utils/schema_alignment.py）；
○ dedup_new：对新增类/关系再做 embedding 去重（避免“支持度高但语义重复”的膨胀）；
○ conflict_policy：冲突处理策略（记录冲突动作/生成冲突报告）。
输出：在 final_dir 写出多版本 p4_tbox_augmented_s{support}allow{0|1}.json，并可输出冲突报告 outputs/ontoqa/p4_conflicts*.json。
与原论文的关系：
● 借鉴：用多源文档增强 schema，并保留证据句（evidence）。
● 调整：我把“专家审核的 8%/10%拒绝”替换为 支持度聚合 + 冲突检测 + 去重报告 的自动化质量控制；原因是要支撑 2~3 小时级别的批处理运行与可复现性。
● 自主设计：断点续跑、聚合文件、冲突报告、merge-only 模式（复用聚合结果，生成不同配置版本）。
关键代码（1）：P4 建议字段设计（Prompt 层）
代码位置：kg/prompts.py（P4_AUGMENT_PROMPT 的输出规范）
每条 suggestions 元素必须包含字段：
type: "class" | "relation" | "attribute"
name: 英文名
cn_name: 中文名
definition: 定义
parent_or_domain_range_or_owner:
class: 父类英文名（或 "DisasterEvent"/"null"）
relation: "DomainClass -> RangeClass"
attribute: owner 类名
value_type:
class/relation: "null"
attribute: "string"/"number"/...
evidence: 原文支撑短句
关键代码（2）：支持度聚合（min_support）的数据结构与意义
代码位置：scripts/run_p4_batch.py（聚合逻辑；此处用“说明性伪代码 + 变量类型”表达）
raw_suggestions: list[dict]，每条来自某一 doc_id 的 P4 suggestions
suggestion_buckets: dict[tuple, dict] = {}

for s in raw_suggestions:
# 1) 取建议的结构化关键字段
s_type = s.get("type") # str: class/relation/attribute
name = s.get("name") # str: 英文名
extra = s.get("parent_or_domain_range_or_owner", "") # str: 父类/签名/owner
range_ = s.get("range", "") # str: 关系的 range（若有）
doc_id = s.get("doc_id", s.get("_source",""))

text

# 2) 定义聚合 key：同一个“概念/关系/属性”在不同文档重复出现 => support 增加
key = (s_type, name, extra, range_)

if key not in suggestion_buckets:
    # 3) 首次出现：support=1，并记录来源文档列表
    s["_support"] = 1                       # int
    s["_support_sources"] = [doc_id]        # list[str]
    suggestion_buckets[key] = s
else:
    # 4) 再次出现：support++，并去重追加来源 doc_id
    suggestion_buckets[key]["_support"] += 1
    if doc_id and doc_id not in suggestion_buckets[key]["_support_sources"]:
        suggestion_buckets[key]["_support_sources"].append(doc_id)
aggregated: list[dict] = list(suggestion_buckets.values())
为什么 support 能作为“自动置信度”：
● 在灾害制度/预案类文本中，真正关键的概念（如“防汛抗旱指挥部”“应急响应级别”“监测预警”）往往跨文档重复出现；
● 单文档里偶然出现的“噪声概念/幻觉概念”更难在多文档重复出现；
因此 min_support>=2 实际上是用“跨文档一致性”过滤一次幻觉/长尾噪声，功能上对应原论文的“专家拒绝比例”，但实现上更自动化。
关键代码（3）：P4 合并策略（allow_new_classes / 对齐 / 去重 / 冲突）
代码位置：kg/cq_pipeline.py（轻量合并函数 apply_p4_suggestions）+ scripts/run_p4_batch.py（更完整的批处理版本）
def apply_p4_suggestions(schema: TBoxSchema, p4_result: Dict[str, Any]) -> TBoxSchema:
# 1) suggestions: list[dict]，每条 dict 是 class/relation/attribute 之一
suggestions = p4_result.get("suggestions", []) or []

text

# 2) 构建索引：便于 O(1) 判断“是否已存在”
class_map: Dict[str, ClassDef] = {c.name: c for c in schema.classes}
rel_map: Dict[str, RelationDef] = {r.name: r for r in schema.relations}
attr_map: Dict[Tuple[str, str], AttributeDef] = {(a.owner, a.name): a for a in schema.attributes}

for item in suggestions:
    s_type = (item.get("type") or "").strip().lower()  # class/relation/attribute
    name = (item.get("name") or "").strip()
    cn_name = (item.get("cn_name") or "").strip()
    definition = (item.get("definition") or "").strip()
    extra = (item.get("parent_or_domain_range_or_owner") or "").strip()

    # 3) 类：新增或补全（并支持补 parent）
    if s_type == "class":
        if name in class_map:
            # 已存在：只在“缺字段”时补齐，避免覆盖已有人工定义
            cls = class_map[name]
            if (not cls.definition) and definition:
                cls.definition = definition
            if extra and (not cls.parent):
                cls.parent = extra
        else:
            # 不存在：创建新类（parent 由 extra 提供；examples 先置空）
            class_map[name] = ClassDef(
                name=name, cn_name=cn_name or name, definition=definition or "", examples=[],
                parent=extra if extra else None,
            )
    # 4) 关系：解析 "Domain -> Range"，并确保 domain/range 类存在（不存在则创建占位类）
    # 5) 属性：按 (owner, name) 去重，新增或补全 value_type
数据流转（P4 批处理全景：从 JSONL 语料到多版本 TBox）
corpus_jsonl: Path (e.g. data/corpus_for_onto/p4_only.jsonl)
▼ (逐行 json.loads)
jsonl_docs: list[dict] # N≈259（示例语料）
▼ (断点续跑筛选)
docs_to_process: list[tuple[int, dict, str]] # (i, doc, doc_id)
▼ (逐文档 LLM 调用)
suggestions_per_doc: list[dict] # 每 doc 0~K 条
▼ (追加写入)
p4_suggestions.jsonl # 每行 1 条 suggestion（含 doc_id/evidence_span 等）
▼ (聚合)
aggregated: list[dict] # 每条带 _support:int, _support_sources:list[str]
▼ (过滤/对齐/去重/冲突策略)
filtered: list[dict]
▼ (合并到 base_tbox)
tbox_aug: TBoxSchema
▼ (多配置写出)
p4_tbox_augmented_s{support}_allow{0|1}.json
阶段 3 的“对比分析：怎么不同、为什么”

语料形态不同：
原论文强调“PDF → MunerU → Markdown”；我采用“预处理后的 JSONL（含上下文与标签）”。
为什么：我后续还要做抽取与问答评测，JSONL 能同时承载 text/context/元数据/标签，便于统一处理。
质量控制手段不同：
原论文：人工拒绝（统计拒绝率）；
我：min_support + conflict_detection + embedding dedup + conflict_report。
为什么：工程上必须支持长时间批处理；我用“跨文档一致性”替代部分人工审核，并把“可能有问题的点”集中输出为冲突报告供抽查。
继承结构在 P4 可能被破坏（非常具体的观察与原因）：
我在 outputs/cq_pipeline/final/p2_tbox_with_hierarchy.json 中已经有较高 IR（示例计算：IR=0.6471），但在某些 P4 增强版本中新增类缺少有效 parent，导致 IR 降低。
原因：P4 prompt 对 class 的 parent 允许填 "null" 或不在现有类集合中的父类名（例如填了 DisasterImpact 但类未创建），从而在 OntoQA 统计时被判为无效继承边。
这在论文写作中应作为“局限性 + 未来工作”（例如：引入“父类对齐/父类补全”机制）明确说明。
阶段 4：TBox 约束下的事件与三元组抽取（P5）
原论文做法
● 方法描述：从新闻等文本抽取实例并填充本体；推断实体关系并存入 Neo4j；用于后续案例警报生成。
● 技术细节：强调将实例映射到本体类/关系，形成可查询的知识图谱。
我的做法
方法描述（更细）：

构建抽取输入文本（可选上下文）：
○ 文本片段来自 JSONL：segment: dict，包含 text/context_before/context_after；
○ 通过结构化标记区分抽取目标：
■ 【待抽取文本】：主抽取目标
■ 【前文参考】/【后文参考】：仅辅助理解

将 TBox 注入 Prompt，强制 predicate/type 受约束：
○ P5_EXTRACTION_PROMPT 中明确：
■ event_type 必须来自 TBox.classes.name；
■ predicate 必须来自 TBox.relations.name；

调用 LLM（JSON 模式）并拿到 events/triples：输出结构固定，便于后续评测与入库。

最小化清洗与一致性校验（关键鲁棒性步骤）：
○ kg/cq_pipeline.py:_sanitize_p5_result() 会：
■ 统一补齐缺失字段（防止下游 KeyError）；
■ 若 event_type 不在类集合：回退到 DisasterEvent（或第一个可用类）；
■ 若 predicate 不在关系集合：标记 _invalid_predicate=True（不直接丢弃，便于错误分析）；
■ 规范 time/space 的内部结构与类型（dict/list 形态固定）。

可选：实体标准化：kg/utils/entity_linking.py 提供地名/术语别名归一，便于图谱融合与统计。
与原论文的关系：
● 借鉴：实例填充 + 本体约束抽取的思想。
● 调整：我以 JSON events/triples 作为 ABox 主产物，而不是直接写 Neo4j；原因是要做抽取 F1、对比实验、可重复评测。
● 自主设计：抽取后的结构清洗与错误标记（_invalid_predicate），显著提升流水线鲁棒性与可诊断性。
关键代码（1）：P5 抽取入口（含“favor_existing_classes”提示策略）
代码位置：kg/cq_pipeline.py:extract_events
def extract_events(self, paragraph: str, schema: TBoxSchema, save_path: Optional[Path] = None, favor_existing_classes: bool = True) -> Dict[str, Any]:

1) schema_json: str，把 TBoxSchema 序列化为 JSON 文本注入 Prompt
schema_json = json.dumps(schema.to_dict(), ensure_ascii=False, indent=2)

2) class_usage_hint: str，通过提示策略控制“保守复用已有类”还是“鼓励使用细粒度类”
if favor_existing_classes:
class_usage_hint = "优先使用 TBox 中已有的类名，不要随意创造新的事件类型；倾向用已有类 + 属性表达。"
else:
class_usage_hint = "允许充分使用 TBox 中新增的细粒度类（如新补充的 HazardFactor 子类等），鼓励细分事件类型。"

3) user_prompt: str，注入 TBox + 事件 schema + 输入文本 + 额外提示
user_prompt = P5_EXTRACTION_PROMPT.format(
schema_json=schema_json,
event_schema=EVENT_SCHEMA_HINT,
input_text=paragraph.strip(),
class_usage_hint=class_usage_hint,
)

4) LLM 调用：json_mode=True，要求只输出 JSON
res = self.client.call("仅输出 JSON，不要解释。", user_prompt)

5) 清洗与约束校验：确保 events/triples 结构稳定，且与 TBox 尽可能一致
res = self._sanitize_p5_result(res, schema)
if save_path:
self._dump_json(res, save_path)
return res

关键代码（2）：结果清洗（字段补齐 + 约束回退 + 错误标记）
代码位置：kg/cq_pipeline.py:_sanitize_p5_result
def _sanitize_p5_result(res: Any, schema: TBoxSchema) -> Dict[str, Any]:
# 1) 类型兜底：如果模型没返回 dict，直接置空，避免下游崩溃
if not isinstance(res, dict):
return {"events": [], "triples": [], "error": "invalid_response_type"}

text

# 2) 结构兜底：events/triples 必须是 list，否则置空
events = res.get("events") if isinstance(res.get("events"), list) else []
triples = res.get("triples") if isinstance(res.get("triples"), list) else []

# 3) 约束集合：允许的 event_type 与 predicate（来自 TBox）
allowed_event_types = {c.name for c in schema.classes if c.name}
allowed_predicates = {r.name for r in schema.relations if r.name}

# 4) event_type 回退：避免出现“模型自造类名”导致评测无法对齐
fallback_event_type = "DisasterEvent" if "DisasterEvent" in allowed_event_types else next(iter(allowed_event_types), "")

cleaned_events: List[Dict[str, Any]] = []
for event_item in events:
    if not isinstance(event_item, dict):
        continue
    ev = dict(event_item)

    # 5) 补齐关键字段（即使为空字符串也要有键）
    ev.setdefault("event_id", "")
    ev.setdefault("event_type", "")
    ev.setdefault("name", "")
    ev.setdefault("source", "")

    # 6) 若 event_type 不在允许集合：回退到 fallback_event_type
    if allowed_event_types and ev["event_type"] not in allowed_event_types:
        ev["event_type"] = fallback_event_type or ev["event_type"]

    # 7) time 必须是 dict，且包含 start_time/end_time 两个键
    time_block = ev.get("time") if isinstance(ev.get("time"), dict) else {}
    time_block.setdefault("start_time", "")
    time_block.setdefault("end_time", "")
    ev["time"] = time_block

    # 8) space 必须是 dict，且 main_stream/tributaries/provinces 都必须是 list[str]
    space_block = ev.get("space") if isinstance(ev.get("space"), dict) else {}
    for key in ["main_stream", "tributaries", "provinces"]:
        if not isinstance(space_block.get(key), list):
            space_block[key] = []
    ev["space"] = space_block

    cleaned_events.append(ev)

cleaned_triples: List[Dict[str, Any]] = []
for triple_item in triples:
    if not isinstance(triple_item, dict):
        continue
    tr = dict(triple_item)
    # 9) 补齐字段，避免后续评测/入库 KeyError
    for key in ["subject", "predicate", "object", "event_id", "evidence"]:
        tr.setdefault(key, "")
    # 10) predicate 不在 TBox：不丢弃，而是标记，便于误差分析
    if allowed_predicates and tr["predicate"] not in allowed_predicates:
        tr["_invalid_predicate"] = True
    cleaned_triples.append(tr)

return {"events": cleaned_events, "triples": cleaned_triples}
数据流转（P5：从 JSONL 片段到 events/triples）
segment: dict

text: str
context_before: str
context_after: str
▼ (拼接/截断)
input_text: str # 带【待抽取文本】标记
▼ (注入 schema_json + prompt)
LLM 输出 raw: str → res: dict
▼ (_sanitize_p5_result)
extraction: dict{
"events": list[dict], # 每个事件字段齐全、类型稳定
"triples": list[dict] # 每条三元组字段齐全；可能含 _invalid_predicate
}
与原论文更具体的差异点（怎么不同、为什么）
我把“抽取结果的结构稳定性”当作工程硬约束：
原论文更偏“本体/知识正确性”；我做批量抽取时，必须保证后续评测/入库脚本不因缺字段而崩溃，所以加入 _sanitize_p5_result 做强制结构化与回退策略。
我显式记录“违反 TBox 的谓词”而不是直接丢弃：
怎么不同：我会给 triple 标记 _invalid_predicate=True。
为什么：论文写作需要“误差分析”，直接丢弃会掩盖模型行为；标记能统计“约束不一致率”，对应原论文的“可信度/幻觉控制”关注点。
阶段 5：评估与问答落地（结构指标 + CQ 覆盖 + 抽取评测 + KG-RAG）
原论文做法
● 评估：OntoQA 结构指标（RR/IR/公理数等）+ CQ 覆盖 + 警报案例效果（可执行建议）
● 对比对象：FDSO/DMDO/OntoCity 等灾害本体
我的做法
评估维度（对应代码）：

OntoQA（TBox 结构指标）
○ 实现：tools/tbox_metrics.py（核心指标）与 tools/ontoqa_metrics.py（批量对比 + 扩展指标）
○ 指标：
■ RR = P / (P + SC)
■ IR = SC / C
■ AR = A / C
○ 我在 IR 上做过关键工程修复：为类补 parent 字段（对应 subClassOf），并在指标工具中兼容 parent/parent_class 与 class_hierarchy 两种层次表达。
CQ 覆盖度（需求对齐）
○ 实现：tools/cq_coverage.py（BGE 向量相似度）
○ 做法：把类/关系/属性转成富语义文本（含 definition、domain→range、parent），与 CQ 问句做最大相似度匹配，多阈值统计覆盖率。
抽取质量（事件/三元组 F1 + 一致性）
○ 实现：scripts/run_full_evaluation.py + tools/abox_metrics.py（此处略，按你的 gold/preds 文件可生成 report）
下游问答落地（GraphRAG）
○ 实现：kg/query.py（GraphRAG） + retrievers/*（BM25/图检索等）
○ 思路：从文本检索找种子实体 → 图多跳扩展 → 把三元组作为证据交给 LLM 生成答案。
评估结果示例（以当前产物为准，可直接写入论文）
带层级的 P2 TBox（用于对齐 IR）
文件：outputs/cq_pipeline/final/p2_tbox_with_hierarchy.json
用 tools/tbox_metrics.py 计算得到：
● C=34, P=25, A=85, SC=22
● RR=0.5319, IR=0.6471, AR=2.5000
某个 P4 增强版本（展示“增强后 IR 下降”的真实现象）
文件：outputs/cq_pipeline/final_with_hierarchy/p4_tbox_augmented_s2_allow1_20251212_154455.json
● C=48, P=19, A=131, SC=6
● RR=0.7600, IR=0.1250, AR=2.7292
补充解释（非常建议写进论文局限性）：该版本新增类较多，但有效 parent 引用不足（且存在 3 条 parent 引用指向不存在父类），导致 IR 被拉低。
与原论文评估方式的差异（怎么不同、为什么）
维度 原论文 我的方法 为什么不同
终端验证 公共警报案例优化 KG-RAG 问答/检索/推理评测 我的研究目标是问答系统，“能否回答 CQ/能否抽取结构化事实”比“警报可执行性”更关键
结构指标统计对象 OWL 本体（含公理/推理） JSON TBox（classes/relations/attributes + parent） 先保证工程可复现；后续可在论文扩展“JSON→OWL”映射与推理一致性验证
去重/审核结果呈现 拒绝率（8%/10%） 去重报告 + 冲突报告 + 支持度统计 更贴近工程流水线日志与可追溯性，便于答辩展示“过程可控”
d) 模块功能与协同（映射到代码文件）
模块 功能描述 关键代码文件 原论文对应关系
CQ 生成（P1） 领域范围 → CQ 列表 kg/cq_pipeline.py, kg/prompts.py 对应原论文 CQ 生成（Stage2 的前置）
CQ→TBox（P2） 从 CQ 归纳 classes/relations/attributes kg/cq_pipeline.py, kg/prompts.py 对应原论文 CQ 驱动扩展（Stage2）
TBox 规范化（P3） 别名归并、关系清洗、过滤悬空元素 kg/cq_pipeline.py, kg/prompts.py 对应原论文“专家整理/一致性保证”的工程化版本
去重（Embedding） 类/关系向量去重（阈值 0.7） kg/utils/deduplication.py, tools/tbox_dedup.py 对齐原论文 embedding 去重思想（但模型不同）
文献增强（P4） 批处理生成 suggestions → 聚合 → 合并 → 多版本输出 scripts/run_p4_batch.py, kg/cq_pipeline.py 对应原论文权威文档富集（Stage3）
冲突检测 检测悬空/重复/孤立/空定义等 kg/utils/conflict_detection.py 对应原论文的人工审核/逻辑一致性检查
抽取（P5） TBox 约束下 events/triples 抽取与清洗 kg/cq_pipeline.py, kg/prompts.py 对应原论文实例填充（Stage4）
实体标准化 地名/灾害术语别名归一 kg/utils/entity_linking.py 论文可作为“知识融合/一致性”补充点
评估 OntoQA + CQ 覆盖 + 抽取 F1 tools/tbox_metrics.py, tools/ontoqa_metrics.py, tools/cq_coverage.py, scripts/run_full_evaluation.py 对应原论文结构评估 + CQ 覆盖（Stage5 的一部分）
KG-RAG 图谱增强问答 kg/query.py, retrievers/*, kg/build_from_json.py 原论文的下游是警报生成；我替换为问答系统验证

e) 关键技术点详解（参数、prompt 设计、工程细节）
技术点 1：LLM 集成与 JSON 强制输出（鲁棒性工程）
原论文做法：GPT-4o + 低温度 + 嵌入去重 + 专家审核。
我的做法（代码级细节）：
● 统一调用层：kg/llm_core.py
○ 支持 OpenAI 兼容接口；
○ 多 Key 轮换、冷却恢复、重试、超时；
○ json_mode=True 时尝试 response_format={"type":"json_object"}，并强制温度为 0.1（降低漂移）。
● JSON 解析层：kg/cq_pipeline.py:LLMJsonClient
○ 去 code fence；
○ 正则截取 JSON 子串兜底；
○ 数组输出自动包一层 {"cqs": ...}（兼容 P1）。
关键参数（来自 configs/cfg.yaml）：
● llm.base_url：OpenAI 兼容地址（示例：LongCat 代理）
● llm.model_name：默认模型
● llm.temperature：默认 0.1（各阶段也可在 llm_per_stage 覆盖）
● llm.max_retries：重试次数
● llm.timeout：超时（秒）
与原论文差异与原因：我更强调“长时批处理不会中断”和“输出必须可解析”，所以把 JSON 强制输出与兜底解析写成基础设施，而不是依赖人工修正模型输出。

技术点 2：向量去重与阈值选择（0.7 的可解释落地）
原论文：text-embedding-3-large + 余弦阈值 0.7。
我：BGE-base-zh-v1.5（768 维）+ 余弦阈值 0.7。
怎么不同：embedding 模型不同，但：
● 都使用“语义向量 + 余弦相似度”；
● 都用阈值 0.7 作为“重复/同义”的经验判定；
● 我额外输出 rejected 项的 _similar_to/_similarity，便于论文展示“去重过滤了哪些概念、为什么被过滤”。

技术点 3：P4 的“支持度聚合（min_support）”作为自动质量控制
原论文：主要靠专家拒绝幻觉候选。
我：min_support>=2 过滤低频建议，并保留 _support_sources 可追溯证据。
为什么有效：灾害制度/预案文本中真正关键概念高复用；幻觉/噪声低复用。
工程收益：
● 显著减少人工审核量；
● 使 P4 能在 259 文档规模上稳定运行（2~3 小时级别）；
● 支持 merge-only 快速生成不同配置版本（allow0/allow1、多 support）。

技术点 4：冲突检测与“可诊断”输出
我用两类机制代替“专家全量审查”：

kg/utils/conflict_detection.py：从 TBox 结构角度找“悬空/重复/孤立/空定义”等问题；

scripts/run_p4_batch.py：生成 conflict_report（例如 parent 冲突、domain/range 冲突），并输出冲突动作日志（用于审计）。
这使得论文写作时可以给出“流程质量控制的可视化证据”，而不是仅凭主观描述。

与原论文方法的系统对比（更具体）
a) 方法本质对比
维度 原论文 我的方法
核心思想 人机协同的半自动化本体工程 CQ 驱动的工程化流水线（P1~P5）+ 可复现评测
方法定位 面向公众风险沟通的洪水本体 面向 KG-RAG 问答的长江水旱灾害 TBox+ABox
“人”在环节中的角色 专家定义边界 + 审核/拒绝候选 我/导师可写领域说明、抽查 review/冲突报告、必要时手工生成带 parent 的 P2
“LLM”在环节中的角色 生成 CQ、提取概念/关系、分类文本、推断关系 生成 CQ、反推 TBox、批量生成增强建议、TBox 约束抽取
“质量控制”的主手段 embedding 去重 + 专家审核 + 推理一致性 JSON 强制输出 + 支持度聚合 + 去重 + 冲突检测 + 结构清洗
b) 具体环节对比（对齐到可执行机制）
环节 原论文 我的方法 我的理由（为什么这样改）
初始本体定义 专家定 6 顶层类 领域说明 → CQ → TBox CQ 更贴近问答目标，迭代快；顶层类可在 P2/P3 中自然浮现并被规范化
CQ 生成 GPT-4o，温度 0.1 多 provider（OpenAI 兼容）+ json_mode + 低温度 工程可控性：统一调用层、可换模型、可断点续跑
实体去重 text-embedding-3-large，阈值 0.7 BGE-base-zh-v1.5，阈值 0.7 成本与语言匹配；仍保留“余弦阈值”可解释逻辑
文档解析 MunerU（PDF→MD） JSONL 语料（预清洗 + 标签 + 上下文） 统一承载多任务信息（增强/抽取/评测），便于工程复用
知识存储 Neo4j JSON（主）→ 可选 NetworkX/Neo4j 先保证评测可复现；再做图数据库落地
质量控制 拒绝率统计 + 专家审核 min_support + 冲突报告 + 去重报告 + 清洗回退 自动化减少人工成本，同时保留可审计证据支撑论文写作
c) 我的方法的特点（可直接写入论文贡献点）
● 借鉴：CQ 驱动、低温度、embedding 去重、文献增强、多源数据思路。
● 简化：减少对 Protégé/OWL 工具链的依赖，用 JSON 表达中间产物以便工程化与批处理。
● 增强：加入断点续跑、支持度聚合、冲突检测、结果清洗、可诊断日志与报告。
● 新增：面向 KG-RAG 的评测闭环（CQ 覆盖 + 抽取 F1 + QA 对比）。
● 未涉及：原论文的“面向公众的警报可执行建议生成”作为最终案例验证（我用问答系统替代）。

实现细节与代码示例（精选关键环节）
a) 项目结构（与方法阶段对齐）
YangtzeDestoryLLM/
├── kg/
│ ├── cq_pipeline.py # P1-P5 核心流水线（CQ→TBox→增强→抽取）
│ ├── prompts.py # P1-P5 Prompt 模板（强约束 JSON 输出）
│ ├── llm_core.py # 统一 LLM 调用层（json_mode/重试/限流/日志）
│ └── utils/
│ ├── deduplication.py # 向量去重（BGE 768维，阈值0.7）

│ ├── schema_alignment.py # 同义对齐（名称归一）
│ ├── conflict_detection.py # 模式冲突检测
│ └── entity_linking.py # 实体标准化（别名归一）
├── scripts/
│ ├── run_p4_batch.py # P4 批处理：断点续跑 + 聚合 + 多版本输出 + 冲突报告
│ ├── manual_p2_to_p3.py # 手工 P2→P3：对“带层级的 P2”做去重并输出报告
│ └── run_full_evaluation.py # 评估：OntoQA + CQ覆盖 + 抽取指标
└── tools/
├── tbox_metrics.py # OntoQA 核心指标 RR/IR/AR
├── ontoqa_metrics.py # 批量对比 + 扩展结构指标（深度/分支/循环等）
└── cq_coverage.py # CQ 覆盖度评估（句向量）
b) 核心代码示例（建议在答辩时重点讲 3 段）

kg/cq_pipeline.py:LLMJsonClient —— 为什么能稳定产出可解析 JSON
kg/utils/deduplication.py —— 为什么“阈值 0.7”可以工程化落地并可解释
scripts/run_p4_batch.py —— 为什么 P4 能 2~3 小时批量运行且可断点续跑
c) 完整数据流转（全景图，便于论文插图）
┌──────────────────────────────────────────────────────────────────────┐
│ 数据流转全景图 │
├──────────────────────────────────────────────────────────────────────┤
│ [输入1] 领域说明 domain_desc:str │
│ ▼ │
│ P1 生成 CQ → p1_cqs.json ({"cqs": list[dict]}) │
│ ▼ │
│ P2 CQ→TBox → p2_tbox_init.json (classes/relations/attributes) │
│ ▼ │
│ P3 规范化 → p3_tbox_normalized.json / p3_tbox_dedup.json │
│ ▼ │
│ [输入2] P4 语料 JSONL: list[dict]（id/text/context/labels...） │
│ ▼ │
│ P4 批处理：逐doc suggestions.jsonl → 聚合 agg.json(_support/来源) │
│ ▼ │
│ 合并生成多版本 TBox → p4_tbox_augmented_s{X}_allow{0|1}.json │
│ ▼ │
│ P5 抽取：input_text(str) + TBox(JSON) → events/triples(JSON) │
│ ▼ │
│ 评估：OntoQA + CQ 覆盖 + 抽取F1 → reports/csv/md/json │
└──────────────────────────────────────────────────────────────────────┘

总结（写给导师/答辩用）
a) 我的方法核心思想（≤20字）
以 CQ 反推 TBox，语料增强并约束抽取。
b) 我的方法流程速记（3-5步）
领域说明 → 生成 CQ（P1）
CQ → 初始 TBox + 规范化/去重（P2/P3）
语料批处理增强 TBox（P4：支持度聚合 + 去重 + 冲突报告）
TBox 约束抽取 events/triples 并清洗（P5）
OntoQA/CQ 覆盖/抽取指标评估，支撑 KG-RAG（Stage5）
c) 与原论文的关系总结（借鉴/调整/自主设计）
类型 具体内容
借鉴 CQ 驱动、低温度、embedding 去重、文献增强、结构指标 + CQ 覆盖评估
调整 顶层类优先 → CQ 优先；权威文档解析 → JSONL 语料批处理；案例警报验证 → QA/抽取评测闭环
自主设计 JSON 强制输出与兜底解析、断点续跑、支持度聚合、冲突报告、抽取结果清洗与错误标记
未涉及 “公众警报可执行建议生成”作为最终案例（被 KG-RAG 问答替代）
d) 我在论文中应强调的主要工作

把“本体构建方法”工程化为 P1~P5 可复现流水线，并形成稳定的中间产物与日志/报告体系。
通过 parent 字段与 OntoQA 工具链，使层级结构（IR）可测量、可对齐论文评价框架。
设计 P4 的支持度聚合与断点续跑，让“多文档增强”在工程上可运行、可追溯、可对比。 我参考的这个基于cq增强的论文是来自water期刊的，我其实应该对比计算机方向的顶级会议、期刊上的论文以及相关模型和方法作为baseline，在其中加入我的模块或者提出一些创新点才能作为我的毕业论文的一章节，我现在不确定这个方法到底好不好，以及我该选择哪些相关的作为baseline。 你的任务为 ：1.仔细调研相关方向（本体论、基于cq增强的kg）等计算机方向的顶级会议、期刊论文，选取模型和方法作为我可以对比的baseline 2.对这些模型和方法进行自己分析和研究，如果我需要选取作为baseline的话需要怎么做，给出全面详细的调研和分析 3、注意：你调研的领域和论文需要尽量丰富和权威，时效需要在2021-2025年之间。