---
license: apache-2.0
datasets:
  train:
  - wenge-research/yayi_uie_sft_data
---

<div align="center">
  <h1>
  雅意IE大模型/YAYI UIE
</h1>
<!-- <br> -->
</div>

<div align="center">
<img src="./assets/yayi_dark_small.png" alt="YaYi" style="width: 30%; display: block; margin: auto;">
<br>

[[🤗Github Repo](https://github.com/wenge-research)]
[[🔗网页端](https://yayi.wenge.com)]

</div>

## 介绍/Introduction
雅意信息抽取统一大模型 (YAYI-UIE)在百万级人工构造的高质量信息抽取数据上进行指令微调，统一训练信息抽取任务包括命名实体识别（NER），关系抽取（RE）和事件抽取（EE），实现通用、安全、金融、生物、医疗、商业、
个人、车辆、电影、工业、餐厅、科学等场景下结构化抽取。

通过雅意IE大模型的开源为促进中文预训练大模型开源社区的发展，贡献自己的一份力量，通过开源，与每一位合作伙伴共建雅意大模型生态。如果您想了解更多关于 YAYI UIE 模型的细节，我们建议您参阅 [GitHub](https://github.com/wenge-research/yayi_uie) 仓库。更多技术细节，欢迎阅读我们的技术报告🔥[YAYI-UIE: A Chat-Enhanced Instruction Tuning Framework for Universal Information Extraction](https://arxiv.org/abs/2312.15548)。

The YAYI Unified Information Extraction Large Language Model (YAYI UIE), fine-tuned on millions of high-quality data, integrates training across tasks such as Named Entity 
Recognition (NER), Relation Extraction (RE), and Event Extraction (EE). The model is able to extract structured outputs across diverse fields including general, security, 
finance, biology, medicine, business, personal, automotive, film, industry, restaurant, and science.

The open-source of YAYI-UIE aims to foster the growth of the Chinese PLM open-source community. We can't wait to collaborate with our partners to develop the YAYI Large Models ecosystem! For more details about the YAYI UIE, please refer to our  [GitHub](https://github.com/wenge-research/yayi_uie)  repository. For more technical details, please read our technical report 🔥YAYI-UIE: A Chat-Enhanced Instruction Tuning Framework for Universal Information Extraction.

![instruction](./assets/YAYI-UIE-1.png)

#### 数据集地址

| 数据集名称 | 大小 | 魔搭模型标识 | 下载地址 |
|:----------|:----------:|:----------:|----------:|
| YAYI-UIE Data | 3.4G    | wenge-research/yayi_uie_sft_data| [数据集下载](https://modelscope.cn/datasets/wenge-research/yayi_uie_sft_data)|

#### 模型推理/Model Inference
```python
>>> import torch
>>> from transformers import AutoModelForCausalLM, AutoTokenizer
>>> from transformers.generation.utils import GenerationConfig
>>> tokenizer = AutoTokenizer.from_pretrained("wenge-research/yayi-uie", use_fast=False, trust_remote_code=True)
>>> model = AutoModelForCausalLM.from_pretrained("wenge-research/yayi-uie", device_map="auto", torch_dtype=torch.bfloat16, trust_remote_code=True)
>>> generation_config = GenerationConfig.from_pretrained("wenge-research/yayi-uie")
>>> prompt = "文本:氧化锆陶瓷以其卓越的物理和化学特性在多个行业中发挥着关键作用。这种材料因其高强度、高硬度和优异的耐磨性，广泛应用于医疗器械、切削工具、磨具以及高端珠宝制品。在制造这种高性能陶瓷时，必须遵循严格的制造标准，以确保其最终性能。这些标准涵盖了从原材料选择到成品加工的全过程，保障产品的一致性和可靠性。氧化锆的制造过程通常包括粉末合成、成型、烧结和后处理等步骤。原材料通常是高纯度的氧化锆粉末，通过精确控制的烧结工艺，这些粉末被转化成具有特定微观结构的坚硬陶瓷。这种独特的微观结构赋予氧化锆陶瓷其显著的抗断裂韧性和耐腐蚀性。此外，氧化锆陶瓷的热膨胀系数与铁类似，使其在高温应用中展现出良好的热稳定性。因此，氧化锆陶瓷不仅在工业领域，也在日常生活中的应用日益增多，成为现代材料科学中的一个重要分支。\n抽取文本中可能存在的实体，并以json{制造品名称/制造过程/制造材料/工艺参数/应用/生物医学/工程特性：[实体]}格式输出。"
>>> # "<reserved_13>" is a reserved token for human, "<reserved_14>" is a reserved token for assistant
>>> prompt = "<reserved_13>" + prompt + "<reserved_14>"
>>> inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
>>> response = model.generate(**inputs, max_new_tokens=512, temperature=0)
>>> print(tokenizer.decode(response[0],skip_special_tokens=True))
```

#### 指令样例/Sample Prompts

1. 实体抽取任务/NER tasks
```
文本：xx
【实体抽取】抽取文本中可能存在的实体，并以json{人物/机构/地点：[实体]}格式输出。
Text:
From the given text, extract all the entities and types. Please format the answer in json {person/organization/location：[entities]}.
```
2. 关系抽取任务/RE tasks
```
文本：xx
【关系抽取】已知关系列表是[注资,拥有,纠纷,自己,增持,重组,买资,签约,持股,交易]。根据关系列表抽取关系三元组，按照json[{'relation':'', 'head':'', 'tail':''}, ]的格式输出。
Text:
From the given text, extract the possible head entities (subjects) and tail entities (objects) and give the corresponding relation triples.The relations are [country of administrative divisions,place of birth,location contains]. Output the result in json[{'relation':'', 'head':'', 'tail':''}, ].
```
```
文本：xx
抽取文本中可能存在的关系，并以json[{'关系':'会见/出席', '头实体':'', '尾实体':''}, ]格式输出。
```
3. 事件抽取任务/EE tasks
```
文本：xx
已知论元角色列表是[质押方,披露时间,质权方,质押物,质押股票/股份数量,事件时间,质押物所属公司,质押物占总股比,质押物占持股比]，请根据论元角色列表从给定的输入中抽取可能的论元，以json{角色:论元,}格式输出。
Text:
Given the text and the role list [seller, place, beneficiary, buyer], identify event arguments and roles, provide your answer in the format of json{role:name}.
```


## 模型zero-shot评测/Zero-shot Evaluation
1. NER任务/NER tasks

AI，Literature，Music，Politics，Science为英文数据集，boson，clue，weibo为中文数据集

AI，Literature,Music,Politics and Science are English datasets; boson，clue and weibo are Chinese datasets

| Model | AI | Literature | Music | Politics | Science | **EN** Average | boson | clue | weibo | **ZH** Average |
| ------ | ------ | ------ | ------ | ------ | ------ | ------ | ------ | ------ | ------ | ------ |
| davinci | 2.97 | 9.87 | 13.83 | 18.42 | 10.04 | 11.03 | - | - | - | 31.09 |
| ChatGPT 3.5 | **54.4** | **54.07** | **61.24** | **59.12** | **63** | **58.37** | 38.53 | 25.44 | 29.3 |
| UIE | 31.14 | 38.97 | 33.91 | 46.28 | 41.56 | 38.37 | 40.64 | 34.91 | 40.79 | 38.78 |
| USM | 28.18 | 56 | 44.93| 36.1 | 44.09 | 41.86 | - | - | - | - |
| InstructUIE |	49 | 47.21 | 53.16 | 48.15 | 49.3 | 49.36 | - | - | - | - |
| DeepKE-LLM | 13.76 | 20.18 | 14.78 | 33.86 | 9.19 | 18.35 | 25.96 | 4.44 | 25.2 | 18.53 |
| YAYI-UIE | 52.4 | 45.99 | 51.2	| 51.82 | 50.53 | 50.39 | **49.25** | **36.46** | 36.78 | **40.83** |

2. RE任务/RE Tasks

FewRe，Wiki-ZSL为英文数据集， SKE 2020，COAE2016，IPRE为中文数据集

FewRe and Wiki-ZSL are English datasets; SKE 2020, COAE2016 and IPRE are Chinese datasets

| Model | FewRel | Wiki-ZSL | **EN** Average | SKE 2020 | COAE2016 | IPRE | **ZH** Average |
| ------ | ------ | ------ | ------ | ------ | ------ | ------ | ------ |
| ChatGPT 3.5 | 9.96 | 13.14 | 11.55  24.47 | 19.31 | 6.73 | 16.84 |
| ZETT(T5-small) | 30.53 | 31.74 | 31.14 | - | - | - | - |
| ZETT(T5-base) | 33.71 | 31.17 | 32.44 | - | - | - | - |
| InstructUIE |**39.55** | 35.2 | 37.38 | - | - | - | - |
| DeepKE-LLM | 17.46 | 15.33 | 16.40 | 0.4 | 6.56 | 9.75 |5.57|
| YAYI-UIE | 36.09 | **41.07** | **38.58** | **70.8** | **19.97** | **22.97**| **37.91**|

3. EE任务/EE Tasks

commodity news为英文数据集，FewFC，ccf_law为中文数据集

commodity news is a English dataset, FewFC and ccf_law are Chinese datasets

EET（事件类型判别 Event Type Extraction）

| 模型 | commodity news | FewFC | ccf_law | **ZH** Average |
| ------ | ------ | ------ | ------ | ------ |
| ChatGPT 3.5 | 1.41 | 16.15 | 0 | 8.08 |
| UIE | - | 50.23 | 2.16 | 26.20 |
|InstructUIE| **23.26** | - | - | - |
| YAYI-UIE | 12.45 | **81.28** | **12.87** | **47.08**|

EEA（事件论元抽取 Event Arguments Extraction）

| 模型 | commodity news | FewFC | ccf_law | **ZH** Average |
| ------ | ------ | ------ | ------ | ------ |
| ChatGPT 3.5 | 8.6 | 44.4 | 44.57 | 44.49 |
| UIE | - | 43.02 | **60.85** | 51.94 |
|InstructUIE| **21.78** | - | - | - |
| YAYI-UIE | 19.74 | **63.06** | 59.42 | **61.24** |

The chart illustrates the performance of our model on Chinese IE tasks in zero-shot setting.

![零样本推理性能分布](./assets/zh-0shot.png)

## 相关协议/Terms and Conditions
#### 局限性/Limitations
基于当前数据和基础模型训练得到的SFT模型，在效果上仍存在以下问题：

1. 抽取的信息可能会产生违背事实的错误回答。
2. 对于具备危害性的指令无法很好的鉴别，可能会产生危害性言论。
3. 在一些涉及段落级长文本的场景下模型的抽取能力仍有待提高。


The SFT model, trained using the data and the base model, still faces the following issues:

1. The information extracted may lead to factually incorrect answers.
2. It struggles to effectively discern harmful instructions, potentially resulting in hazardous statements.
3. The model's extraction capability needs improvement in scenarios involving paragraph-level texts.

#### 开源协议/Open Source License
本项目中的代码和数据依照 [Apache-2.0](LICENSE) 协议开源，社区使用YAYI UIE模型或其衍生品请遵循[Baichuan2](https://github.com/baichuan-inc/Baichuan2)的社区协议和商用协议。
The code and data in this project is open-sourced under the [Apache-2.0](LICENSE) license. The use of YAYI-UIE model or its derivatives must adhere to [Baichuan2](https://github.com/baichuan-inc/Baichuan2)'s community and commercial Model License.

#### 免责声明/Disclaimer
基于以上模型局限性，我们要求开发者仅将我们开源的代码、数据、模型及后续用此项目生成的衍生物用于研究目的，不得用于商业用途，以及其他会对社会带来危害的用途。请谨慎鉴别和使用雅意大模型生成的内容，请勿将生成的有害内容传播至互联网。若产生不良后果，由传播者自负。
本项目仅可应用于研究目的，项目开发者不承担任何因使用本项目（包含但不限于数据、模型、代码等）导致的危害或损失。详细请参考免责声明。

Given the limitations of the model outlined above,we require developers to use the code, data, models, and any derivatives generated from this project solely for research 
purposes. They must not be used for commercial purposes or other applications that could harm society. Users should be careful in discerning and utilizing content generated 
by the YAYI UIE, and avoid distributing harmful content on the internet. The spreader bears sole responsibility for any adverse consequences.

This project is intended only for research purposes. The project developers are not liable for any harm or loss resulting from the use of this project, including but not 
limited to data, models, and code. For more details, please refer to the disclaimer.

## 引用/Citation

如果您在工作中使用了我们的模型，请引用我们的论文:

If you are using the resource for your work, please cite our paper.

```
@article{YAYI-UIE,
  author    = {Xinglin Xiao, Yijie Wang, Nan Xu, Yuqi Wang, Hanxuan Yang, Minzheng Wang, Yin Luo, Lei Wang, Wenji Mao, Dajun Zeng}},
  title     = {YAYI-UIE: A Chat-Enhanced Instruction Tuning Framework for Universal Information Extraction},
  journal   = {arXiv preprint arXiv:2312.15548},
  url       = {https://arxiv.org/abs/2312.15548},
  year      = {2023}
}
```

