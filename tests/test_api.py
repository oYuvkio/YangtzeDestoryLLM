#!/usr/bin/env python3
"""
API 测试脚本

测试两种调用方式：
1. OpenAI SDK 方式（与项目代码一致）
2. requests POST 方式（直接 HTTP 调用）

使用方法：
    python tests/test_longcat_api.py
    python tests/test_longcat_api.py --api-key YOUR_KEY
"""
import os
import sys
import argparse
import json
from typing import Optional

# =============================================================================
# 配置
# =============================================================================
# 【直接修改这里来配置 API Key、URL 和模型】
API_KEY = "sk-ZsW81LLT3Pv16LpkJYGngngk4VRrKuLeSDapEHTTuFuQBz6J"  # 直接在这里填入你的 API Key
DEFAULT_BASE_URL = "https://api.uglycat.cc/v1"  # 修改这里来测试不同的 URL
DEFAULT_MODEL = "gemini-2.5-flash"  # 修改这里来测试不同的模型
TEST_PROMPT = """你是一名水旱灾害知识图谱本体工程师，现有模式如下：
{
  \"classes\": [
    {
      \"name\": \"DisasterEvent\",
      \"cn_name\": \"灾害事件\",
      \"definition\": \"在一定时间和空间范围内发生的与长江流域相关的水旱灾害过程\",
      \"examples\": [
        \"1998年长江特大洪水\",
        \"2022年长江流域特大干旱\"
      ],
      \"parent\": null
    },
    {
      \"name\": \"GeographicEntity\",
      \"cn_name\": \"地理实体\",
      \"definition\": \"长江流域相关的各类地理要素，包括水体、行政区域等\",
      \"examples\": [
        \"长江流域\",
        \"鄱阳湖\",
        \"湖北省\"
      ],
      \"parent\": null
    },
    {
      \"name\": \"RiverBasin\",
      \"cn_name\": \"流域\",
      \"definition\": \"由分水岭围成的河流集水区域\",
      \"examples\": [
        \"长江流域\",
        \"汉江流域\",
        \"嘉陵江流域\"
      ],
      \"parent\": \"GeographicEntity\"
    },
    {
      \"name\": \"Lake\",
      \"cn_name\": \"湖泊\",
      \"definition\": \"长江流域内的天然湖泊\",
      \"examples\": [
        \"鄱阳湖\",
        \"洞庭湖\",
        \"太湖\"
      ],
      \"parent\": \"GeographicEntity\"
    },
    {
      \"name\": \"HazardFactor\",
      \"cn_name\": \"致灾因子\",
      \"definition\": \"导致水旱灾害发生或加剧的各类自然和人为因素\",
      \"examples\": [
        \"厄尔尼诺事件\",
        \"极端降水\",
        \"围湖造田\"
      ],
      \"parent\": null
    },
    {
      \"name\": \"PrecipitationAnomaly\",
      \"cn_name\": \"降水异常\",
      \"definition\": \"降水量明显偏离多年平均值的气象现象\",
      \"examples\": [
        \"汛期降水偏多\",
        \"连续干旱少雨\",
        \"极端暴雨事件\"
      ],
      \"parent\": \"HazardFactor\"
    },
    {
      \"name\": \"EconomicLoss\",
      \"cn_name\": \"经济损失\",
      \"definition\": \"灾害造成的直接和间接经济损失\",
      \"examples\": [
        \"1998年洪水直接经济损失\",
        \"农作物损失\",
        \"货运量损失\"
      ],
      \"parent\": \"DisasterImpact\"
    },
    {
      \"name\": \"Casualty\",
      \"cn_name\": \"人员伤亡\",
      \"definition\": \"灾害导致的人员死亡、失踪和受伤情况\",
      \"examples\": [
        \"洪水死亡人数\",
        \"转移安置人口\"
      ],
      \"parent\": \"DisasterImpact\"
    },
    {
      \"name\": \"AgriculturalImpact\",
      \"cn_name\": \"农业影响\",
      \"definition\": \"灾害对农业生产造成的影响，包括灌溉用水短缺和粮食减产等\",
      \"examples\": [
        \"受灾农田面积\",
        \"粮食减产量\",
        \"灌溉缺水\"
      ],
      \"parent\": \"DisasterImpact\"
    },
    {
      \"name\": \"WaterConservancyFacility\",
      \"cn_name\": \"水利设施\",
      \"definition\": \"用于防洪抗旱的各类水利工程设施\",
      \"examples\": [
        \"三峡水库\",
        \"荆江大堤\",
        \"荆江分洪区\"
      ],
      \"parent\": null
    },
    {
      \"name\": \"ReservoirGroup\",
      \"cn_name\": \"水库群\",
      \"definition\": \"由多个水库组成的联合调度体系\",
      \"examples\": [
        \"长江上游水库群\",
        \"清江梯级水库群\"
      ],
      \"parent\": \"WaterConservancyFacility\"
    },
    {
      \"name\": \"FloodDetentionArea\",
      \"cn_name\": \"蓄滞洪区\",
      \"definition\": \"用于临时蓄滞洪水以削减洪峰的特定区域\",
      \"examples\": [
        \"荆江分洪区\",
        \"洪湖分蓄洪区\",
        \"杜家台分洪区\"
      ],
      \"parent\": \"WaterConservancyFacility\"
    },
    {
      \"name\": \"HydrologicalStation\",
      \"cn_name\": \"水文站\",
      \"definition\": \"用于监测和记录水文要素的观测站点\",
      \"examples\": [
        \"宜昌站\",
        \"汉口站\",
        \"大通站\"
      ],
      \"parent\": null
    },
    {
      \"name\": \"EmergencyManagement\",
      \"cn_name\": \"应急管理\",
      \"definition\": \"水旱灾害应急响应和管理的相关要素\",
      \"examples\": [
        \"防汛Ⅰ级应急响应\",
        \"洪水红色预警\",
        \"防汛应急预案\"
      ],
      \"parent\": null
    },
    {
      \"name\": \"EmergencyResponseLevel\",
      \"cn_name\": \"应急响应级别\",
      \"definition\": \"根据灾害严重程度划分的应急响应等级\",
      \"examples\": [
        \"防汛Ⅰ级响应\",
        \"防汛Ⅱ级响应\",
        \"抗旱Ⅲ级响应\"
      ],
      \"parent\": \"EmergencyManagement\"
    },
    {
      \"name\": \"VulnerabilityFactor\",
      \"cn_name\": \"脆弱性因素\",
      \"definition\": \"影响区域抗灾能力的脆弱性因素\",
      \"examples\": [
        \"人口密度高\",
        \"设防标准不足\",
        \"防洪设施老化\"
      ],
      \"parent\": null
    }
  ],
  \"relations\": [
    {
      \"name\": \"occurs_in\",
      \"cn_name\": \"发生于\",
      \"domain\": \"DisasterEvent\",
      \"range\": \"GeographicEntity\",
      \"definition\": \"灾害事件发生的地理位置或区域\",
      \"functional\": false
    },
    {
      \"name\": \"has_cause\",
      \"cn_name\": \"致灾因子\",
      \"domain\": \"DisasterEvent\",
      \"range\": \"HazardFactor\",
      \"definition\": \"导致该灾害事件发生的主要因素\",
      \"functional\": false
    },
    {
      \"name\": \"located_in\",
      \"cn_name\": \"位于\",
      \"domain\": \"WaterConservancyFacility\",
      \"range\": \"GeographicEntity\",
      \"definition\": \"水利设施所在的地理位置\",
      \"functional\": false
    },
    {
      \"name\": \"monitors\",
      \"cn_name\": \"监测\",
      \"domain\": \"HydrologicalStation\",
      \"range\": \"River\",
      \"definition\": \"水文站对河流水文要素的监测\",
      \"functional\": true
    },
    {
      \"name\": \"triggers\",
      \"cn_name\": \"触发响应\",
      \"domain\": \"DisasterEvent\",
      \"range\": \"EmergencyResponseLevel\",
      \"definition\": \"灾害事件触发的应急响应级别\",
      \"functional\": false
    },
    {
      \"name\": \"tributary_of\",
      \"cn_name\": \"汇入\",
      \"domain\": \"River\",
      \"range\": \"River\",
      \"definition\": \"支流汇入干流的关系\",
      \"functional\": true
    },
    {
      \"name\": \"belongs_to_basin\",
      \"cn_name\": \"所属流域\",
      \"domain\": \"River\",
      \"range\": \"RiverBasin\",
      \"definition\": \"河流所属的流域\",
      \"functional\": true
    },
    {
      \"name\": \"correlated_with\",
      \"cn_name\": \"统计关联\",
      \"domain\": \"ClimateEvent\",
      \"range\": \"DisasterEvent\",
      \"definition\": \"气候事件与灾害事件发生频率之间的统计相关性\",
      \"functional\": false
    },
    {
      \"name\": \"controls_for\",
      \"cn_name\": \"调控对象\",
      \"domain\": \"Reservoir\",
      \"range\": \"River\",
      \"definition\": \"水库对河流洪水或水量的调控关系\",
      \"functional\": false
    },
    {
      \"name\": \"applies_to\",
      \"cn_name\": \"适用于\",
      \"domain\": \"EmergencyPlan\",
      \"range\": \"DisasterEvent\",
      \"definition\": \"应急预案适用的灾害事件类型\",
      \"functional\": false
    },
    {
      \"name\": \"includes_reservoir\",
      \"cn_name\": \"包含水库\",
      \"domain\": \"ReservoirGroup\",
      \"range\": \"Reservoir\",
      \"definition\": \"水库群包含的单个水库\",
      \"functional\": false
    },
    {
      \"name\": \"risk_level_of\",
      \"cn_name\": \"风险评估\",
      \"domain\": \"RiskLevel\",
      \"range\": \"AdministrativeRegion\",
      \"definition\": \"行政区域的风险等级评估\",
      \"functional\": false
    },
    {
      \"name\": \"within\",
      \"cn_name\": \"隶属于\",
      \"domain\": \"AdministrativeRegion\",
      \"range\": \"AdministrativeRegion\",
      \"definition\": \"下级行政区隶属于上级行政区的关系\",
      \"functional\": true
    },
    {
      \"name\": \"aggravates\",
      \"cn_name\": \"加剧风险\",
      \"domain\": \"HumanActivity\",
      \"range\": \"DisasterEvent\",
      \"definition\": \"人为活动对灾害风险的加剧作用\",
      \"functional\": false
    },
    {
      \"name\": \"connects_lake\",
      \"cn_name\": \"连通湖泊\",
      \"domain\": \"River\",
      \"range\": \"Lake\",
      \"definition\": \"河流与湖泊的水系连通关系\",
      \"functional\": false
    },
    {
      \"name\": \"issued_by\",
      \"cn_name\": \"发布机构\",
      \"domain\": \"WarningSignal\",
      \"range\": \"Organization\",
      \"definition\": \"预警信号的发布机构\",
      \"functional\": true
    },
    {
      \"name\": \"has_vulnerability\",
      \"cn_name\": \"具有脆弱性\",
      \"domain\": \"AdministrativeRegion\",
      \"range\": \"VulnerabilityFactor\",
      \"definition\": \"区域存在的脆弱性因素\",
      \"functional\": false
    },
    {
      \"name\": \"impacts_lake\",
      \"cn_name\": \"影响湖泊\",
      \"domain\": \"DisasterEvent\",
      \"range\": \"Lake\",
      \"definition\": \"灾害事件对湖泊水位等的影响\",
      \"functional\": false
    },
    {
      \"name\": \"damages\",
      \"cn_name\": \"损毁设施\",
      \"domain\": \"DisasterEvent\",
      \"range\": \"Infrastructure\",
      \"definition\": \"灾害事件对基础设施的破坏\",
      \"functional\": false
    }
  ],
  \"attributes\": [
    {
      \"owner\": \"DisasterEvent\",
      \"name\": \"start_time\",
      \"cn_name\": \"开始时间\",
      \"value_type\": \"datetime\"
    },
    {
      \"owner\": \"DisasterEvent\",
      \"name\": \"end_time\",
      \"cn_name\": \"结束时间\",
      \"value_type\": \"datetime\"
    },
    {
      \"owner\": \"DisasterEvent\",
      \"name\": \"duration_days\",
      \"cn_name\": \"持续天数\",
      \"value_type\": \"integer\"
    },
    {
      \"owner\": \"FloodEvent\",
      \"name\": \"peak_discharge\",
      \"cn_name\": \"洪峰流量\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"FloodEvent\",
      \"name\": \"days_above_warning\",
      \"cn_name\": \"超警天数\",
      \"value_type\": \"integer\"
    },
    {
      \"owner\": \"FloodEvent\",
      \"name\": \"flood_type\",
      \"cn_name\": \"洪水类型\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"FloodEvent\",
      \"name\": \"occurrence_frequency\",
      \"cn_name\": \"发生频率\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"FloodEvent\",
      \"name\": \"flood_intensity\",
      \"cn_name\": \"洪水强度\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"DroughtEvent\",
      \"name\": \"drought_grade\",
      \"cn_name\": \"干旱等级\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"DroughtEvent\",
      \"name\": \"spatial_distribution\",
      \"cn_name\": \"空间分布特征\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"DroughtEvent\",
      \"name\": \"interannual_pattern\",
      \"cn_name\": \"年际变化规律\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"DroughtEvent\",
      \"name\": \"periodicity\",
      \"cn_name\": \"周期性特征\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"Reservoir\",
      \"name\": \"flood_control_capacity\",
      \"cn_name\": \"防洪库容\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"Reservoir\",
      \"name\": \"total_capacity\",
      \"cn_name\": \"总库容\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"Reservoir\",
      \"name\": \"operation_mode\",
      \"cn_name\": \"调度运用方式\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"Levee\",
      \"name\": \"total_length\",
      \"cn_name\": \"总长度\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"Levee\",
      \"name\": \"grade\",
      \"cn_name\": \"等级\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"Levee\",
      \"name\": \"compliance_rate\",
      \"cn_name\": \"达标率\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"Levee\",
      \"name\": \"protection_standard\",
      \"cn_name\": \"设防标准\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"FloodDetentionArea\",
      \"name\": \"area\",
      \"cn_name\": \"面积\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"FloodDetentionArea\",
      \"name\": \"detention_capacity\",
      \"cn_name\": \"蓄洪容量\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"FloodDetentionArea\",
      \"name\": \"activation_condition\",
      \"cn_name\": \"启用条件\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"FloodDetentionArea\",
      \"name\": \"design_diversion_flow\",
      \"cn_name\": \"设计分洪流量\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"HydrologicalStation\",
      \"name\": \"station_name\",
      \"cn_name\": \"站名\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"HydrologicalStation\",
      \"name\": \"warning_water_level\",
      \"cn_name\": \"警戒水位\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"HydrologicalStation\",
      \"name\": \"guarantee_water_level\",
      \"cn_name\": \"保证水位\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"HydrologicalStation\",
      \"name\": \"annual_max_water_level\",
      \"cn_name\": \"年最高水位\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"EconomicLoss\",
      \"name\": \"direct_loss_amount\",
      \"cn_name\": \"直接经济损失\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"EconomicLoss\",
      \"name\": \"gdp_percentage\",
      \"cn_name\": \"GDP占比\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"EconomicLoss\",
      \"name\": \"cargo_volume_loss\",
      \"cn_name\": \"货运量损失\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"Casualty\",
      \"name\": \"death_count\",
      \"cn_name\": \"死亡人数\",
      \"value_type\": \"integer\"
    },
    {
      \"owner\": \"Casualty\",
      \"name\": \"missing_count\",
      \"cn_name\": \"失踪人数\",
      \"value_type\": \"integer\"
    },
    {
      \"owner\": \"Casualty\",
      \"name\": \"affected_population\",
      \"cn_name\": \"受灾人口\",
      \"value_type\": \"integer\"
    },
    {
      \"owner\": \"Casualty\",
      \"name\": \"relocated_population\",
      \"cn_name\": \"转移安置人口\",
      \"value_type\": \"integer\"
    },
    {
      \"owner\": \"AgriculturalImpact\",
      \"name\": \"affected_farmland_area\",
      \"cn_name\": \"受灾农田面积\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"AgriculturalImpact\",
      \"name\": \"grain_loss\",
      \"cn_name\": \"粮食损失\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"AgriculturalImpact\",
      \"name\": \"irrigation_shortage\",
      \"cn_name\": \"灌溉缺水量\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"InfrastructureDamage\",
      \"name\": \"damage_type\",
      \"cn_name\": \"破坏类型\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"InfrastructureDamage\",
      \"name\": \"damage_scale\",
      \"cn_name\": \"损失规模\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"WaterSupplyImpact\",
      \"name\": \"shipping_interruption_days\",
      \"cn_name\": \"航运中断天数\",
      \"value_type\": \"integer\"
    },
    {
      \"owner\": \"WaterSupplyImpact\",
      \"name\": \"power_outage_duration\",
      \"cn_name\": \"停电时长\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"EmergencyResponseLevel\",
      \"name\": \"level_name\",
      \"cn_name\": \"级别名称\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"EmergencyResponseLevel\",
      \"name\": \"trigger_condition\",
      \"cn_name\": \"启动条件\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"EmergencyResponseLevel\",
      \"name\": \"response_measures\",
      \"cn_name\": \"响应措施\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"WarningSignal\",
      \"name\": \"signal_level\",
      \"cn_name\": \"信号级别\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"WarningSignal\",
      \"name\": \"signal_color\",
      \"cn_name\": \"信号颜色\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"WarningSignal\",
      \"name\": \"issue_criteria\",
      \"cn_name\": \"发布标准\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"WarningSignal\",
      \"name\": \"issue_procedure\",
      \"cn_name\": \"发布流程\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"EmergencyPlan\",
      \"name\": \"plan_name\",
      \"cn_name\": \"预案名称\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"EmergencyPlan\",
      \"name\": \"decision_procedure\",
      \"cn_name\": \"决策程序\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"EmergencyPlan\",
      \"name\": \"execution_standard\",
      \"cn_name\": \"执行标准\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"EmergencyPlan\",
      \"name\": \"recovery_procedure\",
      \"cn_name\": \"恢复重建程序\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"EmergencyPlan\",
      \"name\": \"funding_mechanism\",
      \"cn_name\": \"资金保障机制\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"OperationSchedule\",
      \"name\": \"schedule_name\",
      \"cn_name\": \"调度名称\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"OperationSchedule\",
      \"name\": \"priority\",
      \"cn_name\": \"优先级\",
      \"value_type\": \"integer\"
    },
    {
      \"owner\": \"OperationSchedule\",
      \"name\": \"coordination_mechanism\",
      \"cn_name\": \"协调机制\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"OperationSchedule\",
      \"name\": \"operation_rules\",
      \"cn_name\": \"调度规则\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"ClimateEvent\",
      \"name\": \"event_type\",
      \"cn_name\": \"事件类型\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"ClimateEvent\",
      \"name\": \"intensity\",
      \"cn_name\": \"强度\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"ClimateEvent\",
      \"name\": \"occurrence_year\",
      \"cn_name\": \"发生年份\",
      \"value_type\": \"integer\"
    },
    {
      \"owner\": \"HumanActivity\",
      \"name\": \"activity_type\",
      \"cn_name\": \"活动类型\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"HumanActivity\",
      \"name\": \"impact_description\",
      \"cn_name\": \"影响描述\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"PrecipitationAnomaly\",
      \"name\": \"anomaly_type\",
      \"cn_name\": \"异常类型\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"PrecipitationAnomaly\",
      \"name\": \"deviation_percentage\",
      \"cn_name\": \"偏离比例\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"River\",
      \"name\": \"river_name\",
      \"cn_name\": \"河流名称\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"River\",
      \"name\": \"length\",
      \"cn_name\": \"长度\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"River\",
      \"name\": \"drainage_area\",
      \"cn_name\": \"流域面积\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"Lake\",
      \"name\": \"lake_name\",
      \"cn_name\": \"湖泊名称\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"Lake\",
      \"name\": \"area\",
      \"cn_name\": \"面积\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"Lake\",
      \"name\": \"normal_water_level\",
      \"cn_name\": \"正常水位\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"RiverBasin\",
      \"name\": \"basin_name\",
      \"cn_name\": \"流域名称\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"RiverBasin\",
      \"name\": \"total_area\",
      \"cn_name\": \"总面积\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"AdministrativeRegion\",
      \"name\": \"region_name\",
      \"cn_name\": \"区域名称\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"AdministrativeRegion\",
      \"name\": \"population_density\",
      \"cn_name\": \"人口密度\",
      \"value_type\": \"float\"
    },
    {
      \"owner\": \"AdministrativeRegion\",
      \"name\": \"flood_protection_standard\",
      \"cn_name\": \"防洪设防标准\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"RiskLevel\",
      \"name\": \"level_name\",
      \"cn_name\": \"等级名称\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"RiskLevel\",
      \"name\": \"classification_criteria\",
      \"cn_name\": \"划分依据\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"VulnerabilityFactor\",
      \"name\": \"factor_name\",
      \"cn_name\": \"因素名称\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"VulnerabilityFactor\",
      \"name\": \"factor_description\",
      \"cn_name\": \"因素描述\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"Organization\",
      \"name\": \"org_name\",
      \"cn_name\": \"机构名称\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"Organization\",
      \"name\": \"responsibility\",
      \"cn_name\": \"职责分工\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"Infrastructure\",
      \"name\": \"facility_type\",
      \"cn_name\": \"设施类型\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"Infrastructure\",
      \"name\": \"flood_exposure\",
      \"cn_name\": \"洪水暴露度\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"DroughtReliefWaterSource\",
      \"name\": \"source_type\",
      \"cn_name\": \"水源类型\",
      \"value_type\": \"string\"
    },
    {
      \"owner\": \"DroughtReliefWaterSource\",
      \"name\": \"supply_capacity\",
      \"cn_name\": \"供水能力\",
      \"value_type\": \"float\"
    }
  ]
}

下面的文本可能包含尚未覆盖的重要概念或关系，请在现有模式基础上给出「补充建议」，而不是完全重写。

待分析文本：
\"2.2 流域防汛抗旱总指挥部

长江、黄河、淮河、海河、珠江、松花江、太湖等流域设立流域防总,负责落实国家防总以及水利部防汛抗旱的有关要求,执行国家防总指令,指挥协调所管辖范围内的防汛抗旱工作。流域防总由有关省、自治区、直辖市人民政府和该流域管理机构等有关单位以及相关战区或其委托的单位负责人等组成,其办事机构(流域防总办公室)设在该流域管理机构。国家防总相关指令统一由水利部下达到各流域防总及其办事机构执行。

2.3 地方各级人民政府防汛抗旱指挥部

有防汛抗旱任务的县级以上地方人民政府设立防汛抗旱指挥部,在上级防汛抗旱指挥机构和本级人民政府的领导下,强化组织、协调、指导、督促职能,指挥本地区的防汛抗旱工作。防汛抗旱指挥部由本级人民政府和有关部门、当地解放军和武警部队等有关单位负责人组成。防汛压力大、病险水库多、抢险任务重、抗旱任务重的地方,政府主要负责同志担任防汛抗旱指挥部指挥长。

乡镇一级人民政府根据当地实际情况明确承担防汛抗旱防台风工作的机构和人员。

2.4 其他防汛抗旱指挥机构

有防汛抗旱任务的部门和单位根据需要设立防汛抗旱机构,在本级或属地人民政府防汛抗旱指挥机构统一领导下开展工作。针对重大突发事件,可以组建临时指挥机构,具体负责应急处理工作。\"

---

任务说明：

1. 从文本中识别出当前 TBox 中尚未很好覆盖的「候选类、关系或属性」。
2. 对每个补充建议，给出：
   - type: \"class\" | \"relation\" | \"attribute\"
   - name: 英文名（类名/关系名/属性名）
   - cn_name: 中文名
   - definition: 简要中文定义（对于关系，可说明主语宾语及语义）
   - parent_or_domain_range_or_owner:
     - 若 type = \"class\"：填该类的父类英文名（若不确定，可填 \"DisasterEvent\" 或 \"null\"）
     - 若 type = \"relation\"：填 \"DomainClass -> RangeClass\" 形式的字符串，例如：
       - \"DisasterEvent -> EmergencyMeasure\"
     - 若 type = \"attribute\"：填该属性所属的类名，例如：
       - \"DisasterEvent\"
   - value_type:
     - 若 type = \"class\" 或 \"relation\"，固定填 \"null\"
     - 若 type = \"attribute\"，从以下枚举中选择：\"string\", \"number\", \"integer\", \"float\", \"boolean\", \"datetime\"
   - evidence:
     - 从原文中复制能支撑该建议的一句话或一个短语（中文）

---

输出格式要求：

1. 仅输出一个 JSON 对象，不要输出额外文字。
2. 顶层必须包含字段 \"suggestions\"，其值是一个数组（可以为空数组）。
3. \"suggestions\" 中每个元素必须包含字段：
   - \"type\"
   - \"name\"
   - \"cn_name\"
   - \"definition\"
   - \"parent_or_domain_range_or_owner\"
   - \"value_type\"
   - \"evidence\"

参考输出结构示例（内容仅供参考）：
{
  \"suggestions\": [
    {
      \"type\": \"class\",
      \"name\": \"EmergencyPlan\",
      \"cn_name\": \"应急预案\",
      \"definition\": \"在灾害发生前预先编制的应对洪水或干旱事件的行动和处置方案\",
      \"parent_or_domain_range_or_owner\": \"ManagementDocument\",
      \"value_type\": \"null\",
      \"evidence\": \"……启动防汛应急预案……\"
    },
    {
      \"type\": \"relation\",
      \"name\": \"triggers_emergency_response\",
      \"cn_name\": \"触发应急响应\",
      \"definition\": \"描述某个阈值条件或事件触发某级别应急响应的关系\",
      \"parent_or_domain_range_or_owner\": \"ThresholdCondition -> EmergencyResponseLevel\",
      \"value_type\": \"null\",
      \"evidence\": \"……当水位达到警戒水位以上时，启动Ⅳ级应急响应……\"
    },
    {
      \"type\": \"attribute\",
      \"name\": \"emergency_level\",
      \"cn_name\": \"应急响应级别\",
      \"definition\": \"表示应急响应的等级，如I级、II级、III级、IV级\",
      \"parent_or_domain_range_or_owner\": \"EmergencyResponse\",
      \"value_type\": \"string\",
      \"evidence\": \"……启动防汛II级应急响应……\"
    }
  ]
}"""
DEFAULT_ENABLE_THINKING=True


def print_header(title: str) -> None:
    """打印分隔标题"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def print_result(success: bool, response: str, duration: float) -> None:
    """打印测试结果"""
    status = "✅ 成功" if success else "❌ 失败"
    print(f"状态: {status}")
    print(f"耗时: {duration:.2f}s")
    print(f"响应: {response[:200]}{'...' if len(response) > 200 else ''}")


# =============================================================================
# 方式一：OpenAI SDK
# =============================================================================
def test_openai_sdk(api_key: str, base_url: str, model: str) -> bool:
    """
    使用 OpenAI SDK 测试 API。
    
    这与项目中 kg/llm_core.py 的调用方式一致。
    """
    print_header("方式一：OpenAI SDK")
    
    try:
        from openai import OpenAI
    except ImportError:
        print("❌ 未安装 openai 库，请先运行: pip install openai")
        return False
    
    import time
    
    print(f"Base URL: {base_url}")
    print(f"Model: {model}")
    print(f"API Key: {api_key[:10]}...{api_key[-4:]}")
    print(f"Prompt: {TEST_PROMPT}")
    print()
    
    try:
        client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        
        start = time.time()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": TEST_PROMPT}
            ],
            #max_tokens=100,
            temperature=0.1,
            #extra_body={"thinking": {"type": "enabled"}}
        )
        duration = time.time() - start
        
        content = response.choices[0].message.content or ""
        print_result(True, content, duration)
        
        # 打印完整响应（调试用）
        print(f"\n完整响应对象:")
        print(f"  - model: {response.model}")
        print(f"  - usage: {response.usage}")
        
        return True
        
    except Exception as e:
        print_result(False, str(e), 0)
        print(f"\n错误详情: {type(e).__name__}: {e}")
        return False


# =============================================================================
# 方式二：requests POST
# =============================================================================
def test_requests_post(api_key: str, base_url: str, model: str) -> bool:
    """
    使用 requests 库直接发送 POST 请求测试 API。
    
    这与 curl 命令等效。
    """
    print_header("方式二：requests POST")
    
    try:
        import requests
    except ImportError:
        print("❌ 未安装 requests 库，请先运行: pip install requests")
        return False
    
    import time
    
    # 构建请求 URL（注意：base_url 已包含 /v1，需要拼接 /chat/completions）
    url = f"{base_url.rstrip('/')}/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    
    data = {
        "model": model,
        "messages": [
            {"role": "user", "content": TEST_PROMPT}
        ],
        "max_tokens": 100,
        "temperature": 0.7,
    }
    
    print(f"URL: {url}")
    print(f"Model: {model}")
    print(f"API Key: {api_key[:10]}...{api_key[-4:]}")
    print(f"Prompt: {TEST_PROMPT}")
    print()
    
    try:
        start = time.time()
        response = requests.post(
            url,
            headers=headers,
            json=data,
            timeout=30,
            #enable_thinking=True
        )
        duration = time.time() - start
        
        # 检查状态码
        if response.status_code != 200:
            print_result(False, f"HTTP {response.status_code}: {response.text}", duration)
            return False
        
        # 解析响应
        result = response.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        print_result(True, content, duration)
        
        # 打印完整响应（调试用）
        print(f"\n完整响应 JSON:")
        print(json.dumps(result, indent=2, ensure_ascii=False)[:500])
        
        return True
        
    except requests.exceptions.Timeout:
        print_result(False, "请求超时", 30)
        return False
    except requests.exceptions.ConnectionError as e:
        print_result(False, f"连接失败: {e}", 0)
        return False
    except Exception as e:
        print_result(False, str(e), 0)
        print(f"\n错误详情: {type(e).__name__}: {e}")
        return False


# =============================================================================
# 方式三：测试项目中的 LLMClient
# =============================================================================
def test_llm_client(api_key: str, base_url: str, model: str) -> bool:
    """
    使用项目中的 LLMClient 测试。
    
    这会验证 kg/llm_core.py 的完整功能。
    """
    print_header("方式三：项目 LLMClient")
    
    # 设置环境变量（LLMClient 从环境变量读取 API Key）
    os.environ["OPENAI_API_KEY"] = api_key
    
    try:
        # 添加项目根目录到路径
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        
        from kg.llm_core import LLMClient
    except ImportError as e:
        print(f"❌ 无法导入 LLMClient: {e}")
        return False
    
    import time
    
    config = {
        "base_url": base_url,
        "model_name": model,
        "temperature": 0.7,
        "max_tokens": 10000,
        "max_retries": 1,
        "timeout": 180,
    }
    
    print(f"Config: {json.dumps(config, indent=2)}")
    print(f"Prompt: {TEST_PROMPT}")
    print()
    
    try:
        client = LLMClient(config)
        
        start = time.time()
        response = client.chat(TEST_PROMPT)
        duration = time.time() - start
        
        if response:
            print_result(True, response, duration)
            return True
        else:
            print_result(False, "响应为空", duration)
            return False
        
    except Exception as e:
        print_result(False, str(e), 0)
        print(f"\n错误详情: {type(e).__name__}: {e}")
        return False


# =============================================================================
# 主函数
# =============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="LongCat API 测试脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python tests/test_longcat_api.py
  python tests/test_longcat_api.py --api-key ak_xxxxx
  python tests/test_longcat_api.py --test openai
  python tests/test_longcat_api.py --test requests
  python tests/test_longcat_api.py --test client
        """
    )
    parser.add_argument(
        "--api-key", "-k",
        default=os.getenv("OPENAI_API_KEY", ""),
        help="API Key（默认从环境变量 OPENAI_API_KEY 读取）"
    )
    parser.add_argument(
        "--base-url", "-u",
        default=DEFAULT_BASE_URL,
        help=f"API Base URL（默认: {DEFAULT_BASE_URL}）"
    )
    parser.add_argument(
        "--model", "-m",
        default=DEFAULT_MODEL,
        help=f"模型名称（默认: {DEFAULT_MODEL}）"
    )
    parser.add_argument(
        "--test", "-t",
        choices=["all", "openai", "requests", "client"],
        default="all",
        help="测试方式: all=全部, openai=SDK, requests=POST, client=LLMClient"
    )
    
    args = parser.parse_args()
    
    # 检查 API Key
    # 优先使用命令行参数，其次使用环境变量，最后使用文件中的默认配置
    if not args.api_key:
        args.api_key = API_KEY
    
    if not args.api_key or args.api_key.startswith("sk-your"):
        print("❌ 未提供有效的 API Key")
        print("请通过以下方式之一提供：")
        print("  1. 直接修改文件: API_KEY = \"你的API Key\"（第 23 行）")
        print("  2. 命令行参数: python tests/test_api.py --api-key YOUR_KEY")
        print("  3. 环境变量: export OPENAI_API_KEY=YOUR_KEY")
        sys.exit(1)
    
    print("\n" + "="*60)
    print("  LongCat API 测试")
    print("="*60)
    print(f"\nAPI Key: {args.api_key[:10]}...{args.api_key[-4:]}")
    print(f"Base URL: {args.base_url}")
    print(f"Model: {args.model}")
    
    results = {}
    
    # 执行测试
    if args.test in ("all", "openai"):
        results["OpenAI SDK"] = test_openai_sdk(args.api_key, args.base_url, args.model)
    
    if args.test in ("all", "requests"):
        results["requests POST"] = test_requests_post(args.api_key, args.base_url, args.model)
    
    if args.test in ("all", "client"):
        results["LLMClient"] = test_llm_client(args.api_key, args.base_url, args.model)
    
    # 打印总结
    print_header("测试总结")
    
    all_passed = True
    for name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("🎉 所有测试通过！")
        return 0
    else:
        print("⚠️  部分测试失败，请检查上面的错误信息")
        return 1


if __name__ == "__main__":
    sys.exit(main())
