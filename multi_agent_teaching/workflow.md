# 1 多智能体框架LangGraph(LangChain)

**LangGraph** 是由 LangChain 团队推出的一个强大扩展库，专门用于构建具备**状态管理**和**多智能体**能力的 LLM 应用程序。



TradingAgents: Multi-Agents LLM Financial Trading Framework

- 该工作的底层代码实现正是基于LangGraph框架

<img src="workflow.assets/image-20260322181720121.png" alt="image-20260322181720121" style="zoom:33%;" />

它**基于图（Graph）**的概念，将 AI 工作流建模为节点（Node）和边（Edge）的有向图结构。

- 节点：每一个节点就是一个Agent，不同Agent的职能是不同的
- 边：边决定了不同Agent之间的交互逻辑，不同的Agent通过图的边相互通信和协作



# 2 智能体设置与交互逻辑

基于LangGraph

**共10个Agent**，从功能上看可以分为**三类**：

1. 分析型智能体
   - 教学信息分析Agent
     - 对教学信息进行解析（教学目标、教学知识点、学情）
   - 教学逻辑规划Agent
     - 规划整张教学地图的构建逻辑
2. 生成型智能体
   - 主干问题生成Agent
   - 支架问题生成Agent
   - 变式问题生成Agent
3. 校验型智能体
   - 对于主干问题设置了三个agent对其进行检验
     - 学生认知对齐检验Agent
     - 教学目标对齐检验Agent
     - 教学逻辑检验Agent
   - 对于支架问题和变式问题，各设置了一个Agent对其生成质量进行检验
     - 变式问题检验Agent
     - 支架问题检验Agent

```mermaid
flowchart TD
A[教学信息分析agent] --> B[教学逻辑规划agent]
B --> C[主干问题生成agent]
C --> D1[学生认知对齐检验agent]
C --> D2[教学目标对齐检验agent]
C --> D3[教学逻辑检验agent]

D1 --> E[主干问题检验汇总]
D2 --> E
D3 --> E

E -->|未通过且未超重试| F[修改有问题的主干问题]
F --> C
E -->|通过| G[支架问题和变式问题生成入口]

G --> H1[变式问题生成agent]
G --> H2[支架问题生成agent]

H1 --> I1[变式问题检验agent]
I1 -->|未通过且未超重试| J1[修改有问题的变式问题]
J1 --> H1
I1 -->|通过| K[双线汇合等待]

H2 --> I2[支架问题检验agent]
I2 -->|未通过且未超重试| J2[修改有问题的支架问题]
J2 --> H2
I2 -->|通过| K

K --> L[教学地图整合]
L --> M[END]

classDef gen fill:#e8f0ff,stroke:#4f46e5,stroke-width:1px,color:#1f2a44;
classDef check fill:#ecfdf5,stroke:#10b981,stroke-width:1px,color:#134e4a;
classDef retry fill:#fff7ed,stroke:#f59e0b,stroke-width:1px,color:#7c2d12;
classDef merge fill:#f5f3ff,stroke:#7c3aed,stroke-width:1px,color:#4c1d95;
classDef analyze fill:#fff1f2,stroke:#e11d48,stroke-width:1px,color:#881337;

class A,B analyze;
class C,H1,H2,L gen;
class D1,D2,D3,I1,I2 check;
class F,J1,J2 retry;
class E,K,M merge,G;
```



```mermaid
flowchart TB
    subgraph P1["阶段一：学情与主干"]
        LA["learning_analysis<br/>学情与目标解析"]
        TLD["teaching_logic_design<br/>教学蓝图规划"]
        MQC["main_question_chain<br/>主干问题链生成"]
        LA --> TLD --> MQC
    end

    subgraph P2["阶段二：主干综合校验与重试"]
        MQCCHK["main_question_check<br/>主干问题综合校验"]
        BMR["bump_main_retry<br/>累计重试 / 保存反馈"]
        MQC --> MQCCHK
        MQCCHK -->|未通过且可重试| BMR
        BMR --> MQC
        MQCCHK -->|通过 或 已达最大重试| FOG
    end

    subgraph P3["阶段三：并行子流水线"]
        FOG["fan_out_gen<br/>系统分发（两条并行）"]

        subgraph VAR["变式分支"]
            VQ["variant_question"]
            VC["variant_check"]
            BVR["bump_variant_retry"]
            MVD["mark_variant_done"]
            VQ --> VC
            VC -->|未通过且可重试| BVR
            BVR --> VQ
            VC -->|通过或放弃重试| MVD
        end

        subgraph SCA["支架分支"]
            SQ["scaffold_question"]
            SCC["scaffold_check"]
            BSR["bump_scaffold_retry"]
            MSD["mark_scaffold_done"]
            SQ --> SCC
            SCC -->|未通过且可重试| BSR
            BSR --> SQ
            SCC -->|通过或放弃重试| MSD
        end

        FOG --> VQ
        FOG --> SQ
        MVD --> ASP["aggregate_sub_pipelines<br/>两条流水线汇合计数"]
        MSD --> ASP
    end

    subgraph P4["阶段四：整合与结束"]
        ASP -->|两条都完成| MI["map_integration<br/>教学地图整合"]
        MI --> ENDN((END))
        ASP -->|仅一条完成| WAIT["wait_more → END<br/>本分支暂结束，等另一条"]
    end

```

