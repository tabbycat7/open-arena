/**
 * mat_main.js — 多智能体教学地图：表单提交、SSE、进度、历史、文字视图、日志
 */

var AGENT_STEPS = [
    "learning_analysis",
    "teaching_logic_design",
    "main_question_chain",
    "main_question_check",
    "main_visual_aid_generation",
    "fan_out_gen",
    "variant_question",
    "scaffold_question",
    "variant_check",
    "scaffold_check",
    "variant_visual_aid_generation",
    "scaffold_visual_aid_generation",
    "aggregate_sub_pipelines",
    "map_integration",
    "priority_assignment",
];

var AGENT_TRACKER_STEPS = [
    "learning_analysis",
    "teaching_logic_design",
    "main_question_chain",
    "main_question_check",
    "main_visual_aid_generation",
    "variant_question",
    "variant_check",
    "variant_visual_aid_generation",
    "scaffold_question",
    "scaffold_check",
    "scaffold_visual_aid_generation",
    "map_integration",
    "priority_assignment",
];

var AGENT_DISPLAY_NAMES = {
    learning_analysis: "学情与目标解析",
    teaching_logic_design: "教学蓝图规划",
    main_question_chain: "主干问题链构建",
    main_question_check: "主干问题综合校验",
    main_visual_aid_generation: "主干交互可视化",
    variant_question: "变式问题生成",
    variant_check: "变式问题检验",
    variant_visual_aid_generation: "变式交互可视化",
    scaffold_question: "支架问题生成",
    scaffold_check: "支架问题检验",
    scaffold_visual_aid_generation: "支架交互可视化",
    map_integration: "教学地图整合",
    priority_assignment: "调度优先级分配",
};

var MAT_GENERATION_PHASES = [
    {
        key: "analysis",
        title: "解析课题与学情",
        description: "小侦察正在拆解学习目标、学生起点和课堂关键障碍 🔍",
        agents: ["learning_analysis"],
    },
    {
        key: "blueprint",
        title: "绘制教学蓝图",
        description: "蓝图设计师正在把目标组织成一条清晰的课堂推进路径 📐",
        agents: ["teaching_logic_design"],
    },
    {
        key: "main",
        title: "搭建主干问题链",
        description: "主干工程师正在让核心问题沿着课堂逻辑逐步连起来，并生成交互可视化 🌳",
        agents: ["main_question_chain", "main_question_check", "main_visual_aid_generation", "bump_main_retry"],
    },
    {
        key: "branches",
        title: "生长变式与支架",
        description: "小园丁正在让变式问题和支架提示从主干上冒芽 🌱",
        agents: [
            "fan_out_gen",
            "variant_question",
            "scaffold_question",
            "variant_check",
            "scaffold_check",
            "variant_visual_aid_generation",
            "scaffold_visual_aid_generation",
            "bump_variant_retry",
            "bump_scaffold_retry",
            "mark_variant_done",
            "mark_scaffold_done",
        ],
    },
    {
        key: "polish",
        title: "校验与打磨",
        description: "打磨匠正在检查目标对齐、难度梯度和课堂可用性 ✨",
        agents: ["aggregate_sub_pipelines"],
    },
    {
        key: "assemble",
        title: "合成教学地图",
        description: "总装工正在收束节点、连线和优先级，准备交付地图 🎁",
        agents: ["map_integration", "priority_assignment"],
    },
];

var MAT_AGENT_PHASE_INDEX = {};
MAT_GENERATION_PHASES.forEach(function (phase, index) {
    phase.agents.forEach(function (agent) {
        MAT_AGENT_PHASE_INDEX[agent] = index;
    });
});

// 6 位智能体的视觉化配置：与 MAT_GENERATION_PHASES 一一对应
var MAT_AGENT_AVATARS = [
    {
        key: "analysis",
        emoji: "🔍",
        name: "学情侦察员",
        idleHint: "随时出发",
        busyHint: "正在解读学情…",
        doneHint: "侦察完成",
        color: "#2563eb",
        bg: "#eff6ff",
        shadow: "rgba(37, 99, 235, 0.45)",
    },
    {
        key: "blueprint",
        emoji: "📐",
        name: "蓝图设计师",
        idleHint: "待接力",
        busyHint: "正在描蓝图…",
        doneHint: "蓝图就绪",
        color: "#0ea5e9",
        bg: "#ecfeff",
        shadow: "rgba(14, 165, 233, 0.4)",
    },
    {
        key: "main",
        emoji: "🌳",
        name: "主干工程师",
        idleHint: "待接力",
        busyHint: "正在搭主干…",
        doneHint: "主干稳了",
        color: "#14b8a6",
        bg: "#f0fdfa",
        shadow: "rgba(20, 184, 166, 0.4)",
    },
    {
        key: "branches",
        emoji: "🌱",
        name: "分支园丁",
        idleHint: "待接力",
        busyHint: "正在冒芽…",
        doneHint: "枝叶舒展",
        color: "#22c55e",
        bg: "#f0fdf4",
        shadow: "rgba(34, 197, 94, 0.4)",
    },
    {
        key: "polish",
        emoji: "✨",
        name: "打磨匠",
        idleHint: "待接力",
        busyHint: "正在精雕…",
        doneHint: "通过校验",
        color: "#f59e0b",
        bg: "#fffbeb",
        shadow: "rgba(245, 158, 11, 0.4)",
    },
    {
        key: "assemble",
        emoji: "🎁",
        name: "总装工",
        idleHint: "待接力",
        busyHint: "正在装箱…",
        doneHint: "地图交付",
        color: "#8b5cf6",
        bg: "#f5f3ff",
        shadow: "rgba(139, 92, 246, 0.4)",
    },
];

// ---------------------------------------------------------------------------
// MatTheater：舞台剧场景化生成过程（替代旧 MatStage）
// ---------------------------------------------------------------------------
var MatStage = (function () {
    var SCENE_KEYS = ["waiting", "analysis", "blueprint", "main", "branches", "polish", "assemble", "complete"];
    var PHASE_TO_SCENE = {
        analysis: "analysis",
        blueprint: "blueprint",
        main: "main",
        branches: "branches",
        polish: "polish",
        assemble: "assemble",
    };
    var SCENE_COLORS = {
        waiting: "#64748b",
        analysis: "#2563eb",
        blueprint: "#0ea5e9",
        main: "#14b8a6",
        branches: "#22c55e",
        polish: "#f59e0b",
        assemble: "#8b5cf6",
        complete: "#22c55e",
    };

    var state = {
        currentScene: "waiting",
        currentPhaseIndex: -1,
        finalized: false,
        mainCount: 0,
        variantCount: 0,
        scaffoldCount: 0,
        analysisTagsDrawn: false,
        blocksSpawned: 0,
        branchSignature: "",
        checksSpawned: 0,
        assemblePiecesSpawned: false,
    };

    function getEl(id) { return document.getElementById(id); }

    function clearChildren(node) {
        if (!node) return;
        while (node.firstChild) node.removeChild(node.firstChild);
    }

    // ---------- Topbar dot progress ----------
    // 顶栏第 1 个圆点为「平台准备」，其后 6 个圆点与 MAT_GENERATION_PHASES（第一步…第六步）一一对应
    function phaseIndexToDotIndex(phaseIndex) {
        return phaseIndex < 0 ? 0 : phaseIndex + 1;
    }

    function updateDots(phaseIndex, isDone) {
        var dotsRoot = getEl("matTheaterDots");
        if (!dotsRoot) return;
        var dots = dotsRoot.querySelectorAll(".mat-dot-step");
        var connectors = dotsRoot.querySelectorAll(".mat-dot-connector");
        var activeDotIndex = phaseIndexToDotIndex(phaseIndex);
        var sceneColor = SCENE_COLORS[state.currentScene] || "#3b82f6";
        dots.forEach(function (dot, idx) {
            dot.classList.remove("is-done", "is-active", "is-error");
            dot.style.setProperty("--scene-color", sceneColor);
            if (isDone || idx < activeDotIndex) {
                dot.classList.add("is-done");
            } else if (idx === activeDotIndex) {
                dot.classList.add("is-active");
            }
        });
        connectors.forEach(function (conn, idx) {
            conn.style.background = (isDone || idx < activeDotIndex) ? "#22c55e" : "#cbd5e1";
        });
    }

    function markDotError(phaseIndex) {
        var dotsRoot = getEl("matTheaterDots");
        if (!dotsRoot) return;
        var dots = dotsRoot.querySelectorAll(".mat-dot-step");
        var dotIndex = phaseIndexToDotIndex(Math.max(phaseIndex, 0));
        if (dots[dotIndex]) {
            dots[dotIndex].classList.remove("is-active");
            dots[dotIndex].classList.add("is-error");
        }
    }

    // ---------- Scene switching ----------
    function switchScene(sceneKey) {
        if (sceneKey === state.currentScene) return;
        var stage = getEl("matTheaterStage");
        if (!stage) return;
        var scenes = stage.querySelectorAll(".mat-scene");
        scenes.forEach(function (scene) {
            if (scene.classList.contains("is-active")) {
                scene.classList.remove("is-active");
                scene.classList.add("is-exiting");
                setTimeout(function () { scene.classList.remove("is-exiting"); }, 600);
            }
        });
        var next = stage.querySelector('[data-scene="' + sceneKey + '"]');
        if (next) {
            setTimeout(function () { next.classList.add("is-active"); }, 80);
        }
        state.currentScene = sceneKey;
    }

    // ---------- Narration bar ----------
    function updateNarration(emoji, name, text) {
        // The bottom bar is now product counters only. Keep this no-op so
        // existing state transitions do not need to branch on DOM shape.
    }

    // ---------- Node counters ----------
    function updateNodeCounters() {
        var counts = { main: state.mainCount, variant: state.variantCount, scaffold: state.scaffoldCount };
        Object.keys(counts).forEach(function (key) {
            var el = document.querySelector('[data-counter="' + key + '"]');
            if (el) el.textContent = String(counts[key]);
        });
    }

    function bumpCounter(key) {
        var el = document.querySelector('[data-counter="' + key + '"]');
        if (!el) return;
        var counterCard = el.closest(".mat-node-counter");
        if (!counterCard) return;
        counterCard.classList.remove("is-bump");
        void counterCard.getBoundingClientRect();
        counterCard.classList.add("is-bump");
        setTimeout(function () { counterCard.classList.remove("is-bump"); }, 600);
    }

    // ---------- Scene-specific animations ----------

    // Act 1: Analysis — show tags on doc cards
    function applyAnalysisTags(analysisResult) {
        if (state.analysisTagsDrawn) return;
        var tags = extractSimpleTags(analysisResult);
        if (!tags.length) return;
        var cards = document.querySelectorAll(".mat-scene-analysis .mat-doc-card");
        tags.slice(0, 3).forEach(function (tag, idx) {
            if (cards[idx]) {
                var tagEl = cards[idx].querySelector(".mat-doc-tag");
                if (tagEl) tagEl.textContent = tag;
                cards[idx].classList.add("has-tag");
            }
        });
        state.analysisTagsDrawn = true;
    }

    function extractSimpleTags(data) {
        var tags = [];
        if (!data) return tags;
        if (typeof data === "string") { tags.push(matClipText(data, 10)); return tags; }
        if (typeof data !== "object" || Array.isArray(data)) return tags;
        function addTag(t) { if (t && tags.length < 3) tags.push(matClipText(t, 10)); }
        if (Array.isArray(data.teaching_goals_breakdown)) {
            data.teaching_goals_breakdown.forEach(function (g) {
                if (g && Array.isArray(g.sub_goals)) g.sub_goals.forEach(function (sg) { if (sg && sg.description) addTag(sg.description); });
            });
        }
        if (tags.length < 3 && data.knowledge_graph && Array.isArray(data.knowledge_graph.nodes)) {
            data.knowledge_graph.nodes.forEach(function (n) { if (n && n.name) addTag(n.name); });
        }
        if (tags.length < 3 && data.teaching_focus && Array.isArray(data.teaching_focus.key_points)) {
            data.teaching_focus.key_points.forEach(function (kp) { addTag(kp.point || kp.name); });
        }
        var fallbacks = [data.teaching_objectives, data.sub_goals, data.learning_goals, data.goals, data.knowledge_points, data.core_knowledge_points];
        for (var i = 0; i < fallbacks.length && tags.length < 3; i++) {
            if (Array.isArray(fallbacks[i])) fallbacks[i].forEach(function (item) { addTag(matQuestionText(item)); });
        }
        return tags.slice(0, 3);
    }

    // Act 2: Blueprint — solidify the path
    function solidifyBlueprint() {
        var path = document.querySelector(".mat-route-line");
        if (path) path.classList.add("is-solid");
        document.querySelectorAll(".mat-route-stop").forEach(function (stop, idx) {
            setTimeout(function () { stop.classList.add("is-plotted"); }, 120 + idx * 120);
        });
    }

    // Act 3: Main — install main-question beams on the workshop rail.
    function spawnBlocks(mainQuestions) {
        var row = getEl("matBlocksRow");
        if (!row || !Array.isArray(mainQuestions)) return;
        var count = mainQuestions.length;
        if (count <= state.blocksSpawned) return;
        for (var i = state.blocksSpawned; i < count; i++) {
            var block = document.createElement("div");
            block.className = "mat-block-item mat-main-node";
            block.style.animationDelay = ((i - state.blocksSpawned) * 0.15) + "s";
            block.innerHTML = '<span class="mat-main-node-label"></span><span class="mat-main-node-pin"></span>';
            block.title = matQuestionText(mainQuestions[i]);
            row.appendChild(block);
        }
        state.blocksSpawned = count;
    }

    function labelBlocks(mainQuestions) {
        var row = getEl("matBlocksRow");
        if (!row) return;
        var blocks = row.querySelectorAll(".mat-block-item");
        mainQuestions.forEach(function (q, idx) {
            if (blocks[idx] && !blocks[idx].classList.contains("is-labeled")) {
                var label = blocks[idx].querySelector(".mat-main-node-label");
                if (label) label.textContent = "M" + (idx + 1);
                blocks[idx].classList.add("is-labeled");
            }
        });
    }

    // Act 4: Branches — render variant/scaffold cards growing from the main rail.
    function spawnBranches(variantCount, scaffoldCount) {
        var cardRoot = getEl("matBranchCards");
        if (!cardRoot) return;
        var total = variantCount + scaffoldCount;
        var signature = variantCount + ":" + scaffoldCount;
        if (!total || signature === state.branchSignature) return;
        var allItems = [];
        for (var v = 0; v < variantCount; v++) allItems.push({ type: "variant", label: "V" + (v + 1) });
        for (var s = 0; s < scaffoldCount; s++) allItems.push({ type: "scaffold", label: "S" + (s + 1) });
        clearChildren(cardRoot);
        allItems.forEach(function (item, idx) {
            var card = document.createElement("div");
            card.className = "mat-branch-card " + (item.type === "variant" ? "is-variant" : "is-scaffold");
            card.style.animationDelay = (idx * 0.08) + "s";
            card.innerHTML = '<span class="mat-branch-card-anchor"></span><strong>' + escapeHtml(item.label) + '</strong><small>' + (item.type === "variant" ? "变式" : "支架") + '</small>';
            cardRoot.appendChild(card);
        });
        state.branchSignature = signature;
    }

    // Act 5: Polish — add check items
    function spawnChecks(labels) {
        var container = getEl("matPolishChecks");
        if (!container) return;
        labels.forEach(function (label, idx) {
            if (idx < state.checksSpawned) return;
            var item = document.createElement("div");
            item.className = "mat-check-item mat-quality-check";
            item.textContent = label;
            container.appendChild(item);
            setTimeout(function () { item.classList.add("is-checked"); }, 300 + idx * 400);
        });
        state.checksSpawned = Math.max(state.checksSpawned, labels.length);
        var stamp = getEl("matQualityStamp");
        if (stamp && labels.length) {
            stamp.textContent = "逐项校验";
            stamp.classList.add("is-active");
        }
    }

    // Act 6: Assemble — send generated pieces into a compact map preview.
    function spawnAssemblePieces() {
        var container = getEl("matAssemblePieces");
        if (!container || state.assemblePiecesSpawned) return;
        var colors = ["#3b82f6", "#14b8a6", "#22c55e", "#f59e0b", "#8b5cf6", "#ef4444"];
        var total = state.mainCount + state.variantCount + state.scaffoldCount;
        var count = Math.min(Math.max(total, 6), 15);
        clearChildren(container);
        for (var i = 0; i < count; i++) {
            var piece = document.createElement("div");
            piece.className = "mat-assemble-piece";
            piece.style.background = colors[i % colors.length];
            piece.style.setProperty("--fly-x", ((Math.random() - 0.5) * 60) + "px");
            piece.style.setProperty("--fly-y", (30 + Math.random() * 30) + "px");
            piece.style.animationDelay = (i * 0.1) + "s";
            container.appendChild(piece);
        }
        state.assemblePiecesSpawned = true;
    }

    function completeAssemble() {
        var target = getEl("matAssembleTarget");
        if (target) target.classList.add("is-ready");
        var stamp = getEl("matQualityStamp");
        if (stamp) {
            stamp.textContent = "通过";
            stamp.classList.add("is-passed");
        }
    }

    // ---------- PLACEHOLDER: old buildRelay was here ----------
    // (The old relay bar code has been removed. The following is a no-op stub
    //  so that any remaining call sites don't error.)
    function buildRelay() { /* no-op: replaced by theater topbar */ }

    // ---------- Build canvas (no-op for theater) ----------
    function buildCanvas() { /* no-op: replaced by theater scenes */ }

    // ---------- Public API ----------
    function init() {
        buildRelay();
        buildCanvas();
        resetSceneState();
        switchScene("waiting");
        updateDots(-1, false);
        updateNarration("🎭", "准备中", "等待开始：6 位智能体准备就绪。");
        updateNodeCounters();
    }

    function resetSceneState() {
        state.currentScene = "waiting";
        state.currentPhaseIndex = -1;
        state.finalized = false;
        state.mainCount = 0;
        state.variantCount = 0;
        state.scaffoldCount = 0;
        state.analysisTagsDrawn = false;
        state.blocksSpawned = 0;
        state.branchSignature = "";
        state.checksSpawned = 0;
        state.assemblePiecesSpawned = false;
        // Clear dynamic content in scenes
        var blocksRow = getEl("matBlocksRow");
        if (blocksRow) clearChildren(blocksRow);
        var branchCards = getEl("matBranchCards");
        if (branchCards) clearChildren(branchCards);
        var checks = getEl("matPolishChecks");
        if (checks) clearChildren(checks);
        var pieces = getEl("matAssemblePieces");
        if (pieces) clearChildren(pieces);
        var target = getEl("matAssembleTarget");
        if (target) target.classList.remove("is-ready");
        // Reset blueprint path
        var bpPath = document.querySelector(".mat-route-line");
        if (bpPath) bpPath.classList.remove("is-solid");
        document.querySelectorAll(".mat-route-stop").forEach(function (stop) {
            stop.classList.remove("is-plotted");
        });
        var stamp = getEl("matQualityStamp");
        if (stamp) {
            stamp.textContent = "校验中";
            stamp.classList.remove("is-active", "is-passed");
        }
        // Reset doc cards
        document.querySelectorAll(".mat-doc-card").forEach(function (card) {
            card.classList.remove("has-tag");
            var tag = card.querySelector(".mat-doc-tag");
            if (tag) tag.textContent = "";
        });
    }

    function setStageHint(text) {
        updateNarration(null, null, text || "");
    }

    function onAgentEvent(payload) {
        payload = payload || {};
        var phaseIndex = getGenerationPhaseIndex(payload.agent || "", AGENT_STEPS.indexOf(payload.agent || ""));
        var phase = MAT_GENERATION_PHASES[phaseIndex] || null;
        if (phaseIndex >= 0) {
            state.currentPhaseIndex = phaseIndex;
            var sceneKey = phase ? PHASE_TO_SCENE[phase.key] : null;
            if (sceneKey) switchScene(sceneKey);
            updateDots(phaseIndex, false);
            var avatar = MAT_AGENT_AVATARS[phaseIndex] || {};
            var bubble = payload.message || (phase ? phase.description : "");
            updateNarration(avatar.emoji || "🤖", avatar.name || (phase ? phase.title : ""), matClipText(bubble, 80));
        } else {
            // Unknown agent — just update narration text
            var txt = payload.message || "";
            if (txt) updateNarration(null, null, matClipText(txt, 80));
        }
        applyOutput(payload);
    }

    function applyOutput(payload) {
        var preview = payload && payload.output_preview;
        if (!preview || typeof preview !== "object" || Array.isArray(preview)) return;

        // Analysis tags
        if (preview.analysis_result && typeof preview.analysis_result === "object") {
            applyAnalysisTags(preview.analysis_result);
        }
        // Blueprint
        if (preview.map_construction_logic && typeof preview.map_construction_logic === "object" && Object.keys(preview.map_construction_logic).length > 0) {
            solidifyBlueprint();
        }
        // Main questions
        if (Array.isArray(preview.main_questions) && preview.main_questions.length) {
            var mc = preview.main_questions.length;
            if (mc > state.mainCount) {
                state.mainCount = mc;
                bumpCounter("main");
                updateNodeCounters();
            }
            spawnBlocks(preview.main_questions);
            labelBlocks(preview.main_questions);
        }
        // Variant / scaffold
        if (Array.isArray(preview.variant_questions) && preview.variant_questions.length) {
            var vc = preview.variant_questions.length;
            if (vc > state.variantCount) {
                state.variantCount = vc;
                bumpCounter("variant");
                updateNodeCounters();
            }
        }
        if (Array.isArray(preview.scaffold_questions) && preview.scaffold_questions.length) {
            var sc = preview.scaffold_questions.length;
            if (sc > state.scaffoldCount) {
                state.scaffoldCount = sc;
                bumpCounter("scaffold");
                updateNodeCounters();
            }
        }
        // Branch scene visualization
        if (state.variantCount + state.scaffoldCount > 0) {
            spawnBranches(state.variantCount, state.scaffoldCount);
        }
        // teaching_map (final)
        if (preview.teaching_map && Array.isArray(preview.teaching_map.nodes)) {
            var mains = 0, variants = 0, scaffolds = 0;
            preview.teaching_map.nodes.forEach(function (n) {
                var t = n.question_type || n.type;
                if (t === "main") mains++;
                else if (t === "variant") variants++;
                else if (t === "scaffold") scaffolds++;
            });
            if (mains > state.mainCount) { state.mainCount = mains; bumpCounter("main"); }
            if (variants > state.variantCount) { state.variantCount = variants; bumpCounter("variant"); }
            if (scaffolds > state.scaffoldCount) { state.scaffoldCount = scaffolds; bumpCounter("scaffold"); }
            updateNodeCounters();
        }
        // Polish checks
        if (state.currentScene === "polish" || (preview.validation_results || preview.main_validation_feedback)) {
            var checkLabels = ["目标对齐", "难度梯度", "问题覆盖", "课堂可用性", "逻辑连贯"];
            spawnChecks(checkLabels);
        }
        // Assemble
        if (state.currentScene === "assemble") {
            spawnAssemblePieces();
        }
    }

    function finalize() {
        if (state.finalized) return;
        state.finalized = true;
        updateDots(MAT_GENERATION_PHASES.length - 1, true);
        completeAssemble();
        setTimeout(function () {
            switchScene("complete");
            updateNarration("🎉", "全部完成", "教学地图已生成完成，正在准备最终视图…");
        }, 600);
    }

    function freezeWithError(opts) {
        opts = opts || {};
        markDotError(Math.max(state.currentPhaseIndex, 0));
        updateNarration("⚠️", opts.freezeHint || "已中断", opts.freezeHint || "生成过程已中断。");
    }

    function reset() {
        init();
    }


    return {
        init: init,
        reset: reset,
        onAgentEvent: onAgentEvent,
        applyOutput: applyOutput,
        finalize: finalize,
        freezeWithError: freezeWithError,
        setStageHint: setStageHint,
    };
})();

var MAT_FIELD_LABELS = {
    subject: "学科",
    grade: "年级",
    teaching_goals: "教学目标",
    student_profile: "学情描述",
    difficulty_analysis: "重难点分析",
    language_style: "语言风格",
    attachment: "附件材料",
    model_id: "生成模型",
    temperature: "生成随机性",
    analysis_result: "学情与目标解析结果",
    map_construction_logic: "教学蓝图规划",
    main_questions: "主干问题",
    variant_questions: "变式问题",
    scaffold_questions: "支架问题",
    variant_question_plan: "变式问题计划",
    scaffold_question_plan: "支架问题计划",
    validation_results: "校验反馈",
    main_validation_feedback: "主干问题反馈",
    variant_validation_feedback: "变式问题反馈",
    scaffold_validation_feedback: "支架问题反馈",
    teaching_map: "教学地图",
    nodes: "问题节点",
    edges: "连接关系",
    priorities: "调度优先级",
    priority_assignments: "调度优先级",
    error: "异常信息",
    status: "执行状态",
    task_id: "任务编号",
};

var COGNITIVE_LABELS = {
    remember: "记忆", understand: "理解", apply: "应用",
    analyze: "分析", evaluate: "评价", create: "创造",
};

var currentTaskId = null;
var eventSource = null;
var currentResult = null;
var isGenerating = false;
var currentStepIndex = -1;
var generationStartTimestampMs = null;
var generationDurationFinalSeconds = null;
var generationDurationTimer = null;
var ACTIVE_TASK_STORAGE_KEY = "teaching_map_active_task_id";
var historyEventsBound = false;
var workspaceLayoutEl = document.getElementById("workspaceLayout");
var languageStyleSelectEl = document.getElementById("language_style");
var customLanguageWrapEl = document.getElementById("languageStyleCustomWrap");
var customLanguageInputEl = document.getElementById("custom_language_style");
var modelPickerEl = document.getElementById("modelPicker");
var modelPickerTriggerEl = document.getElementById("modelPickerTrigger");
var modelPickerMenuEl = document.getElementById("modelPickerMenu");
var modelPickerLabelEl = document.getElementById("modelPickerLabel");
var modelPickerIconEl = document.getElementById("modelPickerIcon");
var modelIdInputEl = document.getElementById("model_id");
var temperatureInputEl = document.getElementById("temperature");
var temperatureValueEl = document.getElementById("temperatureValue");
var temperatureHintEl = document.getElementById("temperatureHint");
var fixedTemperatureModels = window.MAT_FIXED_TEMPERATURE_MODELS || {};
var defaultTemperature = Number(window.MAT_DEFAULT_TEMPERATURE);
var markdownOptionsApplied = false;
var managedFiles = [];
var lastInputRecordId = null;
var historyDrawerLoaded = false;
var currentWizardStep = 1;

var LANGUAGE_STYLE_PRESETS = ["严谨学术", "生动活泼", "通俗易懂", "启发引导"];
var MAT_FORM_STEP_META = {
    1: {
        label: "第 1 步",
        title: "基础设置",
        hint: "先确定学科、年级与生成参数。",
        next: "下一步：教学内容",
    },
    2: {
        label: "第 2 步",
        title: "教学内容",
        hint: "写清目标、学情和课堂难点。",
        next: "下一步：附件与生成",
    },
    3: {
        label: "第 3 步",
        title: "附件与生成",
        hint: "补充材料并开始生成教学地图。",
        next: "",
    },
};

var API_PREFIX = "/api/mat";

function formatDurationClock(totalSeconds) {
    var safeSeconds = Math.max(0, Math.round(totalSeconds));
    var hours = Math.floor(safeSeconds / 3600);
    var minutes = Math.floor((safeSeconds % 3600) / 60);
    var seconds = safeSeconds % 60;
    if (hours > 0) {
        return String(hours).padStart(2, "0") + ":" + String(minutes).padStart(2, "0") + ":" + String(seconds).padStart(2, "0");
    }
    return String(minutes).padStart(2, "0") + ":" + String(seconds).padStart(2, "0");
}

function renderGenerationDurationText() {
    var el = document.getElementById("generationDurationText");
    if (!el) return;

    if (typeof generationDurationFinalSeconds === "number" && isFinite(generationDurationFinalSeconds)) {
        el.textContent = "本次用时：" + formatDurationClock(generationDurationFinalSeconds);
        return;
    }

    if (typeof generationStartTimestampMs === "number" && isFinite(generationStartTimestampMs)) {
        var elapsedSeconds = (Date.now() - generationStartTimestampMs) / 1000;
        el.textContent = "本次用时：" + formatDurationClock(elapsedSeconds);
        return;
    }

    el.textContent = "本次用时：--";
}

function clearGenerationDurationTicker() {
    if (generationDurationTimer) {
        clearInterval(generationDurationTimer);
        generationDurationTimer = null;
    }
}

function startGenerationDurationTimer(startTimestampMs) {
    var parsedStart = Number(startTimestampMs);
    if (!isFinite(parsedStart) || parsedStart <= 0) {
        parsedStart = Date.now();
    }
    generationStartTimestampMs = parsedStart;
    generationDurationFinalSeconds = null;
    clearGenerationDurationTicker();
    renderGenerationDurationText();
    generationDurationTimer = setInterval(function () {
        renderGenerationDurationText();
    }, 1000);
}

function finalizeGenerationDuration(durationSeconds) {
    var parsedDuration = Number(durationSeconds);
    if (isFinite(parsedDuration) && parsedDuration >= 0) {
        generationDurationFinalSeconds = parsedDuration;
    } else if (typeof generationStartTimestampMs === "number" && isFinite(generationStartTimestampMs)) {
        generationDurationFinalSeconds = Math.max(0, (Date.now() - generationStartTimestampMs) / 1000);
    } else {
        generationDurationFinalSeconds = null;
    }
    clearGenerationDurationTicker();
    renderGenerationDurationText();
}

function resetGenerationDurationDisplay() {
    generationStartTimestampMs = null;
    generationDurationFinalSeconds = null;
    clearGenerationDurationTicker();
    renderGenerationDurationText();
}

function normalizeStartedAtMs(rawStartedAtTs) {
    var parsed = Number(rawStartedAtTs);
    if (!isFinite(parsed) || parsed <= 0) {
        return Date.now();
    }
    return parsed * 1000;
}

function setUiStage(stage) {
    if (!workspaceLayoutEl) return;
    workspaceLayoutEl.classList.remove("mat-stage-input", "mat-stage-generation");
    if (stage === "generation") {
        workspaceLayoutEl.classList.add("mat-stage-generation");
        return;
    }
    workspaceLayoutEl.classList.add("mat-stage-input");
}

function updateLanguageStyleCustomVisibility() {
    if (!languageStyleSelectEl || !customLanguageWrapEl || !customLanguageInputEl) return;
    var isCustom = languageStyleSelectEl.value === "自定义";
    customLanguageWrapEl.style.display = isCustom ? "block" : "none";
    customLanguageInputEl.required = isCustom;
    if (!isCustom) {
        customLanguageInputEl.value = "";
    }
    triggerFormProgressRefresh();
}

function setStopButtonsState(visible, disabled, text) {
    ["stopBtn", "stopBtnTop"].forEach(function (id) {
        var btn = document.getElementById(id);
        if (!btn) return;
        if (!visible) {
            btn.style.display = "none";
        } else {
            btn.style.display = id === "stopBtn" ? "block" : "inline-flex";
        }
        btn.disabled = !!disabled;
        btn.textContent = text || "强制停止";
    });
}

function setBackToGenerationButtonState(visible) {
    var btn = document.getElementById("backToGenerationBtn");
    if (!btn) return;
    btn.style.display = visible ? "block" : "none";
}

function normalizeTemperatureValue(value, fallback) {
    var parsed = Number(value);
    if (!isFinite(parsed)) parsed = fallback;
    if (!isFinite(parsed)) parsed = 0.7;
    if (parsed < 0) parsed = 0;
    if (parsed > 2) parsed = 2;
    return parsed;
}

function formatTemperatureValue(value) {
    var normalized = normalizeTemperatureValue(value, 0.7);
    return String(Math.round(normalized * 100) / 100);
}

function syncTemperatureSliderUi() {
    if (!temperatureInputEl) return;
    var fallback = normalizeTemperatureValue(defaultTemperature, 0.7);
    var normalized = normalizeTemperatureValue(temperatureInputEl.value, fallback);
    temperatureInputEl.value = formatTemperatureValue(normalized);
    if (temperatureValueEl) {
        temperatureValueEl.textContent = formatTemperatureValue(normalized);
    }
    var min = normalizeTemperatureValue(temperatureInputEl.min, 0);
    var max = normalizeTemperatureValue(temperatureInputEl.max, 2);
    var percent = 0;
    if (max > min) {
        percent = ((normalized - min) / (max - min)) * 100;
    }
    if (!isFinite(percent)) {
        percent = 0;
    }
    percent = Math.max(0, Math.min(100, percent));
    temperatureInputEl.style.setProperty("--value-percent", percent.toFixed(2) + "%");
}

function handleTemperatureInputChange() {
    if (!temperatureInputEl) return;
    var locked = temperatureInputEl.dataset.locked === "1";
    if (locked) {
        var fixedValue = temperatureInputEl.dataset.fixedValue || "1";
        temperatureInputEl.value = fixedValue;
    } else {
        var fallback = normalizeTemperatureValue(defaultTemperature, 0.7);
        temperatureInputEl.value = formatTemperatureValue(
            normalizeTemperatureValue(temperatureInputEl.value, fallback)
        );
    }
    syncTemperatureSliderUi();
}

function updateTemperatureControlForModel(modelId) {
    if (!temperatureInputEl) return;

    var key = modelId || "";
    var hasFixed = Object.prototype.hasOwnProperty.call(fixedTemperatureModels, key);
    if (hasFixed) {
        var fixedValue = normalizeTemperatureValue(fixedTemperatureModels[key], 1);
        temperatureInputEl.value = formatTemperatureValue(fixedValue);
        temperatureInputEl.dataset.locked = "1";
        temperatureInputEl.dataset.fixedValue = formatTemperatureValue(fixedValue);
        temperatureInputEl.setAttribute("aria-disabled", "true");
        temperatureInputEl.classList.add("is-locked");
        syncTemperatureSliderUi();
        if (temperatureHintEl) {
            temperatureHintEl.textContent = "当前模型固定 temperature=" + formatTemperatureValue(fixedValue) + "，不可修改。";
        }
        return;
    }

    temperatureInputEl.dataset.locked = "0";
    delete temperatureInputEl.dataset.fixedValue;
    temperatureInputEl.removeAttribute("aria-disabled");
    temperatureInputEl.classList.remove("is-locked");
    if (!temperatureInputEl.value) {
        var fallback = normalizeTemperatureValue(defaultTemperature, 0.7);
        temperatureInputEl.value = formatTemperatureValue(fallback);
    }
    syncTemperatureSliderUi();
    if (temperatureHintEl) {
        temperatureHintEl.textContent = "控制生成随机性，范围 0~2，数值越高越发散。";
    }
}

function setModelPickerValue(modelId, label, iconUrl) {
    if (modelIdInputEl) {
        modelIdInputEl.value = modelId || "";
        markFieldValidity(modelIdInputEl, !!modelIdInputEl.value);
        modelIdInputEl.dispatchEvent(new Event("input", { bubbles: true }));
        modelIdInputEl.dispatchEvent(new Event("change", { bubbles: true }));
    }
    if (modelPickerLabelEl) modelPickerLabelEl.textContent = label || "请选择模型";
    if (modelPickerIconEl && iconUrl) modelPickerIconEl.src = iconUrl;
    updateTemperatureControlForModel(modelId || "");

    if (!modelPickerMenuEl) return;
    modelPickerMenuEl.querySelectorAll(".mat-model-picker-item").forEach(function (item) {
        var active = item.dataset.value === (modelId || "");
        item.classList.toggle("active", active);
        item.setAttribute("aria-selected", active ? "true" : "false");
    });
}

function closeModelPicker() {
    if (!modelPickerEl || !modelPickerTriggerEl) return;
    modelPickerEl.classList.remove("open");
    modelPickerTriggerEl.setAttribute("aria-expanded", "false");
}

function syncModelPickerFromInput() {
    if (!modelPickerMenuEl || !modelIdInputEl) return;
    var target = modelPickerMenuEl.querySelector('.mat-model-picker-item[data-value="' + modelIdInputEl.value + '"]');
    if (!target) {
        target = modelPickerMenuEl.querySelector(".mat-model-picker-item");
    }
    if (!target) return;
    setModelPickerValue(target.dataset.value, target.dataset.label, target.dataset.icon);
}

function initModelPicker() {
    if (!modelPickerEl || !modelPickerTriggerEl || !modelPickerMenuEl || !modelIdInputEl) {
        updateTemperatureControlForModel(modelIdInputEl ? modelIdInputEl.value : "");
        return;
    }

    modelPickerTriggerEl.addEventListener("click", function () {
        var willOpen = !modelPickerEl.classList.contains("open");
        if (willOpen) {
            modelPickerEl.classList.add("open");
            modelPickerTriggerEl.setAttribute("aria-expanded", "true");
        } else {
            closeModelPicker();
        }
    });

    modelPickerMenuEl.querySelectorAll(".mat-model-picker-item").forEach(function (item) {
        item.addEventListener("click", function () {
            setModelPickerValue(item.dataset.value, item.dataset.label, item.dataset.icon);
            closeModelPicker();
        });
    });

    document.addEventListener("click", function (event) {
        if (!modelPickerEl.contains(event.target)) {
            closeModelPicker();
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            closeModelPicker();
        }
    });

    syncModelPickerFromInput();
}

if (temperatureInputEl) {
    if (!isFinite(defaultTemperature)) {
        defaultTemperature = 0.7;
    }
    if (!temperatureInputEl.value) {
        temperatureInputEl.value = formatTemperatureValue(defaultTemperature);
    }
    syncTemperatureSliderUi();
    temperatureInputEl.addEventListener("input", handleTemperatureInputChange);
    temperatureInputEl.addEventListener("change", handleTemperatureInputChange);
}

// ---------------------------------------------------------------------------
// History drawer
// ---------------------------------------------------------------------------
function setHistoryDrawerOpen(open) {
    var drawer = document.getElementById("historyDrawer");
    var overlay = document.getElementById("historyDrawerOverlay");
    var trigger = document.getElementById("historyDrawerToggle");
    if (!drawer || !overlay) return;

    drawer.classList.toggle("is-open", !!open);
    drawer.setAttribute("aria-hidden", open ? "false" : "true");
    overlay.hidden = !open;
    overlay.classList.toggle("is-open", !!open);
    document.body.classList.toggle("mat-history-drawer-open", !!open);
    if (trigger) trigger.setAttribute("aria-expanded", open ? "true" : "false");

    if (open && !historyDrawerLoaded) {
        historyDrawerLoaded = true;
        loadHistory();
    }
    if (open && isGenerating) {
        var banner = document.getElementById("generatingBanner");
        var bannerText = document.getElementById("generatingBannerText");
        if (banner) banner.style.display = "flex";
        if (bannerText) bannerText.textContent = "正在生成教学地图，当前查看的是历史记录";
    }
}

function openHistoryDrawer() {
    setHistoryDrawerOpen(true);
}

function closeHistoryDrawer() {
    closeAllMoreMenus();
    setHistoryDrawerOpen(false);
}

function toggleHistoryDrawer() {
    var drawer = document.getElementById("historyDrawer");
    setHistoryDrawerOpen(!(drawer && drawer.classList.contains("is-open")));
}

(function initHistoryDrawer() {
    var trigger = document.getElementById("historyDrawerToggle");
    var closeBtn = document.getElementById("historyDrawerClose");
    var overlay = document.getElementById("historyDrawerOverlay");
    if (trigger) trigger.addEventListener("click", toggleHistoryDrawer);
    if (closeBtn) closeBtn.addEventListener("click", closeHistoryDrawer);
    if (overlay) overlay.addEventListener("click", closeHistoryDrawer);
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") closeHistoryDrawer();
    });
})();

// ---------------------------------------------------------------------------
// View mode tabs (graph / text / logs)
// ---------------------------------------------------------------------------
function ensureHistoryResultLoaded(recordId) {
    if (!recordId) return Promise.resolve(null);
    if (currentResult && currentTaskId === recordId) return Promise.resolve(currentResult);

    return fetch(API_PREFIX + "/history/" + recordId)
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data && !data.error && data.result) {
                currentResult = data.result;
                return currentResult;
            }
            return null;
        })
        .catch(function () { return null; });
}

document.querySelectorAll(".mat-view-tab").forEach(function (btn) {
    btn.addEventListener("click", function () {
        document.querySelectorAll(".mat-view-tab").forEach(function (b) { b.classList.remove("active"); });
        this.classList.add("active");
        var mode = this.dataset.view;
        document.getElementById("graphSection").style.display = mode === "graph" ? "block" : "none";
        document.getElementById("textSection").style.display = mode === "text" ? "block" : "none";
        document.getElementById("logsSection").style.display = mode === "logs" ? "block" : "none";
        if (mode !== "graph") {
            document.getElementById("detailSection").style.display = "none";
        }

        if (mode === "graph") {
            if (currentResult) {
                renderGraph(currentResult);
                if (typeof chartInstance !== "undefined" && chartInstance) {
                    chartInstance.resize();
                }
            } else if (currentTaskId) {
                ensureHistoryResultLoaded(currentTaskId).then(function (result) {
                    if (!result) return;
                    renderGraph(result);
                    if (typeof chartInstance !== "undefined" && chartInstance) {
                        chartInstance.resize();
                    }
                });
            }
        }

        if (mode === "text") {
            if (currentResult) {
                renderTextView(currentResult);
                requestAnimationFrame(fitAllInteractiveFrames);
            } else if (currentTaskId) {
                ensureHistoryResultLoaded(currentTaskId).then(function (result) {
                    if (!result) return;
                    renderTextView(result);
                    requestAnimationFrame(fitAllInteractiveFrames);
                });
            }
        }

        if (mode === "logs" && currentTaskId) {
            ensureHistoryResultLoaded(currentTaskId);
            loadAgentLogs(currentTaskId);
        }
    });
});

// ---------------------------------------------------------------------------
// Form submission
// ---------------------------------------------------------------------------
document.getElementById("generateForm").addEventListener("submit", function (e) {
    e.preventDefault();
    startGeneration();
});

document.getElementById("newPlanBtn").addEventListener("click", function () {
    startNewPlan();
});

document.getElementById("stopBtn").addEventListener("click", function () {
    forceStopTask();
});

document.getElementById("stopBtnTop").addEventListener("click", function () {
    forceStopTask();
});

document.getElementById("backToInputBtn").addEventListener("click", function () {
    setUiStage("input");
});

document.getElementById("backToGenerationBtn").addEventListener("click", function () {
    returnToProgress();
});

if (languageStyleSelectEl) {
    languageStyleSelectEl.addEventListener("change", updateLanguageStyleCustomVisibility);
    updateLanguageStyleCustomVisibility();
}

initModelPicker();

// ---------------------------------------------------------------------------
// Form wizard — one focused step at a time
// ---------------------------------------------------------------------------
function getWizardStepForField(field) {
    var section = field ? field.closest(".mat-form-section[data-section]") : null;
    return section ? parseInt(section.dataset.section, 10) : 1;
}

function isRequiredFieldFilled(field) {
    if (!field || field.disabled) return true;
    if (field.tagName === "SELECT") return !!field.value;
    if (field.type === "file") return !!(field.files && field.files.length);
    return !!(field.value && field.value.trim());
}

function markFieldValidity(field, isValid) {
    if (!field) return;
    field.classList.toggle("is-invalid", !isValid);
    var picker = field.id === "model_id" ? document.getElementById("modelPickerTrigger") : null;
    if (picker) picker.classList.toggle("is-invalid", !isValid);
}

function validateWizardStep(step, focusInvalid) {
    var section = document.querySelector('.mat-form-section[data-section="' + step + '"]');
    if (!section) return true;
    var fields = section.querySelectorAll("[required]");
    var firstInvalid = null;

    fields.forEach(function (field) {
        var valid = isRequiredFieldFilled(field);
        markFieldValidity(field, valid);
        if (!valid && !firstInvalid) firstInvalid = field;
    });

    if (firstInvalid && focusInvalid) {
        setWizardStep(step);
        var focusTarget = firstInvalid.id === "model_id" ? document.getElementById("modelPickerTrigger") : firstInvalid;
        setTimeout(function () {
            if (focusTarget && typeof focusTarget.focus === "function") focusTarget.focus();
            if (firstInvalid && firstInvalid.type !== "hidden" && typeof firstInvalid.reportValidity === "function") {
                firstInvalid.reportValidity();
            }
        }, 30);
    }
    return !firstInvalid;
}

function validateWizardForm() {
    var requiredFields = document.querySelectorAll("#generateForm [required]");
    var firstInvalid = null;
    requiredFields.forEach(function (field) {
        var valid = isRequiredFieldFilled(field);
        markFieldValidity(field, valid);
        if (!valid && !firstInvalid) firstInvalid = field;
    });
    if (!firstInvalid) return true;
    validateWizardStep(getWizardStepForField(firstInvalid), true);
    return false;
}

function refreshFieldCounts() {
    document.querySelectorAll(".mat-field-count[data-count-target]").forEach(function (counter) {
        var target = document.getElementById(counter.dataset.countTarget);
        var length = target && target.value ? target.value.trim().length : 0;
        counter.textContent = length + " 字";
    });
}

function setWizardStep(step) {
    var normalized = Math.max(1, Math.min(3, parseInt(step, 10) || 1));
    currentWizardStep = normalized;
    var meta = MAT_FORM_STEP_META[normalized] || MAT_FORM_STEP_META[1];

    document.querySelectorAll(".mat-form-section[data-section]").forEach(function (section) {
        section.classList.toggle("is-active", section.dataset.section === String(normalized));
    });

    document.querySelectorAll(".mat-form-step").forEach(function (btn) {
        btn.classList.toggle("is-active", btn.dataset.step === String(normalized));
    });

    var label = document.getElementById("matCurrentStepLabel");
    var title = document.getElementById("matCurrentStepTitle");
    var hint = document.getElementById("matCurrentStepHint");
    if (label) label.textContent = meta.label;
    if (title) title.textContent = meta.title;
    if (hint) hint.textContent = meta.hint;

    var prevBtn = document.getElementById("wizardPrevBtn");
    var nextBtn = document.getElementById("wizardNextBtn");
    var submitBtn = document.getElementById("submitBtn");
    if (prevBtn) prevBtn.style.display = normalized > 1 ? "inline-flex" : "none";
    if (nextBtn) {
        nextBtn.style.display = normalized < 3 ? "inline-flex" : "none";
        nextBtn.textContent = meta.next;
    }
    if (submitBtn) submitBtn.style.display = normalized === 3 ? "flex" : "none";
}

(function initFormWizard() {
    var stepButtons = document.querySelectorAll(".mat-form-step");
    var prevBtn = document.getElementById("wizardPrevBtn");
    var nextBtn = document.getElementById("wizardNextBtn");
    var form = document.getElementById("generateForm");

    stepButtons.forEach(function (btn) {
        btn.addEventListener("click", function () {
            var targetStep = parseInt(btn.dataset.step, 10);
            if (targetStep > currentWizardStep && !validateWizardStep(currentWizardStep, true)) return;
            setWizardStep(targetStep);
        });
    });

    if (prevBtn) {
        prevBtn.addEventListener("click", function () {
            setWizardStep(currentWizardStep - 1);
        });
    }

    if (nextBtn) {
        nextBtn.addEventListener("click", function () {
            if (!validateWizardStep(currentWizardStep, true)) return;
            setWizardStep(currentWizardStep + 1);
        });
    }

    if (form) {
        form.addEventListener("input", function (event) {
            markFieldValidity(event.target, true);
            refreshFieldCounts();
        });
        form.addEventListener("change", function (event) {
            var target = event.target;
            var valid = !target.hasAttribute || !target.hasAttribute("required") || isRequiredFieldFilled(target);
            markFieldValidity(target, valid);
            refreshFieldCounts();
        });
    }

    refreshFieldCounts();
    setWizardStep(1);
})();

// ---------------------------------------------------------------------------
// Progress ring — tracks required-field completion
// ---------------------------------------------------------------------------
(function initProgressRing() {
    var ring = document.getElementById("formProgressRing");
    var text = document.getElementById("formProgressText");
    if (!ring || !text) return;

    var CIRCUMFERENCE = 2 * Math.PI * 16;
    ring.setAttribute("stroke-dasharray", CIRCUMFERENCE.toFixed(2));
    ring.setAttribute("stroke-dashoffset", CIRCUMFERENCE.toFixed(2));

    var form = document.getElementById("generateForm");

    function update() {
        var requiredFields = form ? form.querySelectorAll("[required]") : [];
        if (!requiredFields.length) return;
        var filled = 0;
        requiredFields.forEach(function (f) {
            if (isRequiredFieldFilled(f)) filled++;
        });
        var ratio = filled / requiredFields.length;
        var offset = CIRCUMFERENCE * (1 - ratio);
        ring.setAttribute("stroke-dashoffset", offset.toFixed(2));
        text.textContent = Math.round(ratio * 100) + "%";

        var stepButtons = document.querySelectorAll(".mat-form-step");
        stepButtons.forEach(function (btn) {
            var secNum = btn.dataset.step;
            var sec = document.querySelector('.mat-form-section[data-section="' + secNum + '"]');
            if (!sec) return;
            var fields = sec.querySelectorAll("[required]");
            var allFilled = fields.length > 0;
            fields.forEach(function (f) {
                if (!isRequiredFieldFilled(f)) allFilled = false;
            });
            btn.classList.toggle("is-done", allFilled && fields.length > 0);
        });
    }

    if (form) {
        form.addEventListener("input", update);
        form.addEventListener("change", update);
    }
    update();
})();

// ---------------------------------------------------------------------------
// Drag-and-drop upload zone
// ---------------------------------------------------------------------------
(function initDropzone() {
    var dropzone = document.getElementById("dropzone");
    var fileInput = document.getElementById("attachment");
    var tagsContainer = document.getElementById("fileTags");
    if (!dropzone || !fileInput || !tagsContainer) return;

    function syncInputFiles() {
        var dt = new DataTransfer();
        managedFiles.forEach(function (f) { dt.items.add(f); });
        fileInput.files = dt.files;
    }

    function renderTags() {
        var html = "";
        managedFiles.forEach(function (file, idx) {
            html += '<span class="mat-file-tag">' + escapeHtml(file.name) +
                '<button type="button" class="mat-file-tag-remove" data-idx="' + idx + '">&times;</button></span>';
        });
        tagsContainer.innerHTML = html;
    }

    function addFiles(fileList) {
        var existingNames = managedFiles.map(function (f) { return f.name; });
        Array.prototype.forEach.call(fileList, function (f) {
            if (existingNames.indexOf(f.name) === -1) {
                managedFiles.push(f);
                existingNames.push(f.name);
            }
        });
        syncInputFiles();
        renderTags();
    }

    fileInput.addEventListener("change", function () {
        if (fileInput.files.length) addFiles(fileInput.files);
    });

    dropzone.addEventListener("dragover", function (e) {
        e.preventDefault();
        dropzone.classList.add("is-dragover");
    });
    dropzone.addEventListener("dragleave", function () {
        dropzone.classList.remove("is-dragover");
    });
    dropzone.addEventListener("drop", function (e) {
        e.preventDefault();
        dropzone.classList.remove("is-dragover");
        if (e.dataTransfer && e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
    });

    tagsContainer.addEventListener("click", function (e) {
        var btn = e.target.closest(".mat-file-tag-remove");
        if (!btn) return;
        var idx = parseInt(btn.dataset.idx, 10);
        if (!isNaN(idx) && idx >= 0 && idx < managedFiles.length) {
            managedFiles.splice(idx, 1);
            syncInputFiles();
            renderTags();
        }
    });
})();

// ---------------------------------------------------------------------------
// Load last input from history
// ---------------------------------------------------------------------------
function clearManagedAttachments() {
    managedFiles = [];
    var fileTags = document.getElementById("fileTags");
    if (fileTags) fileTags.innerHTML = "";
    var attachment = document.getElementById("attachment");
    if (attachment) attachment.value = "";
}

function triggerFormProgressRefresh() {
    document.querySelectorAll("#generateForm [required]").forEach(function (field) {
        field.dispatchEvent(new Event("input", { bubbles: true }));
        field.dispatchEvent(new Event("change", { bubbles: true }));
    });
}

function applyMatInputRecord(record) {
    if (!record) return;

    var subjectEl = document.getElementById("subject");
    var gradeEl = document.getElementById("grade");
    var goalsEl = document.getElementById("teaching_goals");
    var profileEl = document.getElementById("student_profile");
    var difficultyEl = document.getElementById("difficulty_analysis");

    if (subjectEl) subjectEl.value = record.subject || "";
    if (gradeEl) gradeEl.value = record.grade || "";
    if (goalsEl) goalsEl.value = record.teaching_goals || "";
    if (profileEl) profileEl.value = record.student_profile || "";
    if (difficultyEl) difficultyEl.value = record.difficulty_analysis || "";

    var style = (record.language_style || "").trim() || "严谨学术";
    if (languageStyleSelectEl) {
        if (LANGUAGE_STYLE_PRESETS.indexOf(style) >= 0) {
            languageStyleSelectEl.value = style;
            if (customLanguageInputEl) customLanguageInputEl.value = "";
        } else {
            languageStyleSelectEl.value = "自定义";
            if (customLanguageInputEl) customLanguageInputEl.value = style;
        }
        updateLanguageStyleCustomVisibility();
    }

    var modelId = (record.model_id || "").trim();
    if (modelId && modelPickerMenuEl) {
        var pickerItem = null;
        modelPickerMenuEl.querySelectorAll(".mat-model-picker-item").forEach(function (el) {
            if (el.dataset.value === modelId) pickerItem = el;
        });
        if (pickerItem) {
            setModelPickerValue(modelId, pickerItem.dataset.label, pickerItem.dataset.icon);
        } else if (modelIdInputEl) {
            modelIdInputEl.value = modelId;
            if (modelPickerLabelEl) modelPickerLabelEl.textContent = modelId;
            updateTemperatureControlForModel(modelId);
        }
    }

    clearManagedAttachments();
    triggerFormProgressRefresh();
    refreshFieldCounts();
}

function switchToFormTab() {
    closeHistoryDrawer();
    var formTab = document.getElementById("formTab");
    if (formTab) formTab.classList.add("active");
}

function setLoadLastInputButtonMeta(enabled, title) {
    var btn = document.getElementById("loadLastInputBtn");
    var hintEl = document.getElementById("lastInputHint");
    if (!btn) return;
    btn.disabled = !enabled;
    if (title) btn.title = title;
    if (hintEl) {
        var hint = title || "";
        hint = hint.replace(/^恢复最近一次输入：/, "最近：");
        hint = hint.replace(/^恢复最近一次填写的教学信息/, "可恢复最近一次填写");
        hint = hint.replace("（不含附件）", "");
        hintEl.textContent = hint || (enabled ? "可恢复最近一次填写" : "暂无可加载记录");
        hintEl.classList.toggle("is-available", !!enabled);
    }
}

function refreshLoadLastInputAvailability() {
    return fetch(API_PREFIX + "/history")
        .then(function (res) {
            return res.json().then(function (data) {
                return { ok: res.ok, status: res.status, data: data };
            });
        })
        .then(function (payload) {
            if (payload.status === 401) {
                lastInputRecordId = null;
                setLoadLastInputButtonMeta(false, "请先登录后使用");
                return;
            }
            if (!payload.ok || !Array.isArray(payload.data) || !payload.data.length) {
                lastInputRecordId = null;
                setLoadLastInputButtonMeta(false, "暂无历史记录可加载");
                return;
            }
            var item = payload.data[0];
            lastInputRecordId = item.id || null;
            var hint = [item.subject, item.grade, item.created_at].filter(Boolean).join(" · ");
            setLoadLastInputButtonMeta(true, hint ? "恢复最近一次输入：" + hint + "（不含附件）" : "恢复最近一次填写的教学信息（不含附件）");
        })
        .catch(function () {
            lastInputRecordId = null;
            setLoadLastInputButtonMeta(false, "历史记录暂不可用");
        });
}

function loadLastInput() {
    var btn = document.getElementById("loadLastInputBtn");
    if (!btn || btn.disabled) return;

    var textEl = btn.querySelector(".mat-load-last-text");
    var origText = textEl ? textEl.textContent : "加载上次输入";
    btn.classList.add("is-loading");
    btn.disabled = true;
    if (textEl) textEl.textContent = "加载中...";

    function finishSuccess(record) {
        applyMatInputRecord(record);
        switchToFormTab();
        btn.classList.remove("is-loading");
        btn.classList.add("is-success");
        if (textEl) textEl.textContent = "已加载";
        setTimeout(function () {
            btn.classList.remove("is-success");
            refreshLoadLastInputAvailability().then(function () {
                if (textEl) textEl.textContent = origText;
            });
        }, 1800);
    }

    function finishError(message) {
        btn.classList.remove("is-loading");
        if (textEl) textEl.textContent = origText;
        refreshLoadLastInputAvailability();
        alert(message || "加载失败");
    }

    if (lastInputRecordId) {
        fetch(API_PREFIX + "/history/" + lastInputRecordId)
            .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
            .then(function (payload) {
                if (!payload.ok || payload.data.error) {
                    finishError("无法读取上次输入记录");
                    return;
                }
                finishSuccess(payload.data);
            })
            .catch(function () { finishError("加载失败，请稍后重试"); });
        return;
    }

    fetch(API_PREFIX + "/history")
        .then(function (res) {
            return res.json().then(function (data) {
                return { ok: res.ok, status: res.status, data: data };
            });
        })
        .then(function (payload) {
            if (payload.status === 401) {
                finishError("请先登录后使用此功能");
                return;
            }
            if (!payload.ok || !Array.isArray(payload.data) || !payload.data.length) {
                finishError("暂无历史记录");
                return;
            }
            finishSuccess(payload.data[0]);
        })
        .catch(function () { finishError("加载失败，请稍后重试"); });
}

(function initLoadLastInput() {
    var btn = document.getElementById("loadLastInputBtn");
    if (!btn) return;
    btn.addEventListener("click", loadLastInput);
    refreshLoadLastInputAvailability();
})();

function setSubmitLoading(loading) {
    var btn = document.getElementById("submitBtn");
    if (!btn) return;
    var iconEl = btn.querySelector(".mat-btn-icon");
    var textEl = btn.querySelector(".mat-btn-text");
    var spinnerEl = btn.querySelector(".mat-btn-spinner");
    if (loading) {
        btn.classList.add("is-loading");
        btn.disabled = true;
        if (iconEl) iconEl.style.display = "none";
        if (textEl) textEl.textContent = "AI 正在规划...";
        if (spinnerEl) spinnerEl.style.display = "inline-flex";
    } else {
        btn.classList.remove("is-loading");
        if (iconEl) iconEl.style.display = "";
        if (spinnerEl) spinnerEl.style.display = "none";
    }
}

function startGeneration() {
    var form = document.getElementById("generateForm");
    if (!validateWizardForm()) return;
    var formData = new FormData(form);
    if (managedFiles.length) {
        formData.delete("attachment");
        managedFiles.forEach(function (file) {
            formData.append("attachment", file, file.name);
        });
    }
    var submitBtn = document.getElementById("submitBtn");

    setSubmitLoading(true);
    document.getElementById("newPlanBtn").style.display = "none";
    setStopButtonsState(true, false, "强制停止");
    setBackToGenerationButtonState(true);
    isGenerating = true;
    setUiStage("generation");

    document.getElementById("placeholder").style.display = "none";
    document.getElementById("progressSection").style.display = "block";
    document.getElementById("viewTabs").style.display = "none";
    hideNavEntryBar();
    document.getElementById("graphSection").style.display = "none";
    document.getElementById("textSection").style.display = "none";
    document.getElementById("logsSection").style.display = "none";
    document.getElementById("detailSection").style.display = "none";
    clearVisibleProgressLog();
    var progressBar = document.getElementById("progressBar");
    if (progressBar) progressBar.style.width = "0%";
    document.getElementById("generatingBanner").style.display = "none";
    document.getElementById("generatingBannerText").textContent = "正在生成教学地图...";
    initProgressTracker();
    updateCurrentAgentCard({
        step_number: 0,
        agent_display_name: "流程初始化",
        message: "已提交任务，正在排队执行。",
        input_preview: null,
        output_preview: { status: "waiting" },
    });
    currentStepIndex = -1;
    currentResult = null;
    startGenerationDurationTimer(Date.now());

    fetch(API_PREFIX + "/generate", { method: "POST", body: formData })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            currentTaskId = data.task_id;
            localStorage.setItem(ACTIVE_TASK_STORAGE_KEY, currentTaskId);
            connectSSE(currentTaskId);
        })
        .catch(function (err) {
            addLogEntry("连接失败: " + err.message, "error");
            setSubmitLoading(false);
            submitBtn.disabled = false;
            var btnText = submitBtn.querySelector(".mat-btn-text");
            if (btnText) btnText.textContent = "开始生成教学地图";
            isGenerating = false;
            resetGenerationDurationDisplay();
            localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
            updateCurrentAgentCard({
                agent_display_name: "连接异常",
                message: "任务创建失败，请稍后重试。",
                output_preview: { error: err.message },
            });
        });
}

// ---------------------------------------------------------------------------
// SSE streaming
// ---------------------------------------------------------------------------
function connectSSE(taskId, fromIndex) {
    if (eventSource) eventSource.close();
    var start = typeof fromIndex === "number" && fromIndex >= 0 ? fromIndex : 0;
    eventSource = new EventSource(API_PREFIX + "/stream/" + taskId + "?from=" + start);
    var maxStepReached = -1;

    eventSource.onmessage = function (event) {
        var data = JSON.parse(event.data);

        if (data.type === "progress") {
            addLogEntry(data.message, "active");
            var stepIdx = AGENT_STEPS.indexOf(data.agent);
            if (stepIdx > maxStepReached) {
                maxStepReached = stepIdx;
            }
            updateProgressBar(maxStepReached, data.agent);
            updateStepTracker(maxStepReached);
            updateCurrentAgentCard(data);
        } else if (data.type === "done") {
            finalizeGenerationDuration(data.duration_seconds);
            addLogEntry("教学地图生成完成！", "done");
            var progressBar = document.getElementById("progressBar");
            if (progressBar) progressBar.style.width = "100%";
            updateStepTracker(AGENT_STEPS.length - 1, true);
            localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
            // 先把"最终 teaching_map"喂给画布，确保 N/M/K 计数和节点完备
            if (data.result) {
                MatStage.applyOutput({ output_preview: { teaching_map: data.result } });
            }
            updateCurrentAgentCard({
                step_number: AGENT_STEPS.length,
                agent_display_name: "流程完成",
                message: "教学地图已生成完成。",
                output_preview: {
                    nodes: data.result && data.result.nodes ? data.result.nodes.length : 0,
                    edges: data.result && data.result.edges ? data.result.edges.length : 0,
                },
            });
            eventSource.close();
            // 礼花 1.2s 后再切到 ECharts 结果图
            if (data.result) {
                setTimeout(function () { showResult(data.result, taskId); }, 1200);
            }
            resetSubmitBtn(true);
        } else if (data.type === "error") {
            finalizeGenerationDuration(data.duration_seconds);
            addLogEntry("生成出错: " + data.message, "error");
            localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
            updateCurrentAgentCard({
                agent_display_name: "执行失败",
                message: data.message || "工作流执行失败",
                output_preview: { status: "error" },
            });
            eventSource.close();
            resetSubmitBtn(false);
        } else if (data.type === "cancelled") {
            finalizeGenerationDuration(data.duration_seconds);
            addLogEntry("任务已强制停止", "error");
            localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
            updateCurrentAgentCard({
                agent_display_name: "任务终止",
                message: data.message || "任务已强制停止",
                output_preview: { status: "cancelled" },
            });
            eventSource.close();
            resetSubmitBtn(false);
        }
    };

    eventSource.onerror = function () {
        addLogEntry("连接断开，尝试获取结果...", "error");
        eventSource.close();
        setTimeout(function () {
            fetch(API_PREFIX + "/result/" + taskId)
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    if (data.status === "done" && data.result) {
                        finalizeGenerationDuration(data.duration_seconds);
                        localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
                        addLogEntry("成功获取结果", "done");
                        showResult(data.result, taskId);
                        resetSubmitBtn(true);
                        return;
                    }
                    if (data.status === "running") {
                        startGenerationDurationTimer(normalizeStartedAtMs(data.started_at_ts));
                        var progress = Array.isArray(data.progress) ? data.progress : [];
                        connectSSE(taskId, progress.length);
                        return;
                    }
                    if (data.status === "cancelled") {
                        finalizeGenerationDuration(data.duration_seconds);
                        localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
                        addLogEntry("任务已强制停止", "error");
                        resetSubmitBtn(false);
                        return;
                    }
                    finalizeGenerationDuration(data.duration_seconds);
                    localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
                    resetSubmitBtn(false);
                })
                .catch(function () {
                    finalizeGenerationDuration();
                    localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
                    resetSubmitBtn(false);
                });
        }, 1000);
    };
}

function returnToProgress() {
    setUiStage("generation");
    closeHistoryDrawer();
    var formTab = document.getElementById("formTab");
    if (formTab) formTab.classList.add("active");

    document.getElementById("placeholder").style.display = "none";
    document.getElementById("progressSection").style.display = "block";
    document.getElementById("viewTabs").style.display = "none";
    hideNavEntryBar();
    document.getElementById("graphSection").style.display = "none";
    document.getElementById("textSection").style.display = "none";
    document.getElementById("logsSection").style.display = "none";
    document.getElementById("detailSection").style.display = "none";
    document.getElementById("generatingBanner").style.display = "none";
}

function resetSubmitBtn(showNewPlanBtn) {
    var btn = document.getElementById("submitBtn");
    var newPlanBtn = document.getElementById("newPlanBtn");
    setSubmitLoading(false);
    btn.disabled = false;
    var btnText = btn.querySelector(".mat-btn-text");
    if (btnText) btnText.textContent = "重新生成";
    isGenerating = false;
    if (showNewPlanBtn) refreshLoadLastInputAvailability();
    clearGenerationDurationTicker();
    setStopButtonsState(false, false, "强制停止");
    setBackToGenerationButtonState(false);
    document.getElementById("generatingBanner").style.display = "none";
    newPlanBtn.style.display = showNewPlanBtn ? "block" : "none";
}

function startNewPlan() {
    if (eventSource) { eventSource.close(); eventSource = null; }
    localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
    isGenerating = false;
    currentTaskId = null;
    currentResult = null;
    currentStepIndex = -1;
    resetGenerationDurationDisplay();
    setUiStage("input");

    document.getElementById("generateForm").reset();
    clearManagedAttachments();
    updateLanguageStyleCustomVisibility();
    syncModelPickerFromInput();
    refreshFieldCounts();
    setWizardStep(1);
    var btn = document.getElementById("submitBtn");
    setSubmitLoading(false);
    btn.disabled = false;
    var btnText = btn.querySelector(".mat-btn-text");
    if (btnText) btnText.textContent = "开始生成教学地图";
    document.getElementById("newPlanBtn").style.display = "none";
    setBackToGenerationButtonState(false);
    clearVisibleProgressLog();
    var progressBar = document.getElementById("progressBar");
    if (progressBar) progressBar.style.width = "0%";
    renderGenerationPhases(-1, false);

    document.getElementById("placeholder").style.display = "flex";
    document.getElementById("progressSection").style.display = "none";
    document.getElementById("viewTabs").style.display = "none";
    hideNavEntryBar();
    document.getElementById("graphSection").style.display = "none";
    document.getElementById("textSection").style.display = "none";
    document.getElementById("logsSection").style.display = "none";
    document.getElementById("detailSection").style.display = "none";
    document.getElementById("generatingBanner").style.display = "none";

    closeHistoryDrawer();
    var formTab = document.getElementById("formTab");
    if (formTab) formTab.classList.add("active");
}

function getRecordIdFromQuery() {
    try {
        return new URLSearchParams(window.location.search).get("record");
    } catch (e) {
        return null;
    }
}

function openRecordFromQueryOnLoad() {
    var recordId = getRecordIdFromQuery();
    if (!recordId) return false;
    loadHistoryItem(recordId);
    return true;
}

function restoreTaskProgressOnLoad() {
    var taskId = localStorage.getItem(ACTIVE_TASK_STORAGE_KEY);
    if (!taskId) return;

    fetch(API_PREFIX + "/result/" + taskId)
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.status === "running") {
                currentTaskId = taskId;
                isGenerating = true;
                startGenerationDurationTimer(normalizeStartedAtMs(data.started_at_ts));
                setUiStage("generation");
                document.getElementById("placeholder").style.display = "none";
                document.getElementById("progressSection").style.display = "block";
                document.getElementById("viewTabs").style.display = "none";
                hideNavEntryBar();
                document.getElementById("graphSection").style.display = "none";
                document.getElementById("textSection").style.display = "none";
                document.getElementById("logsSection").style.display = "none";
                document.getElementById("detailSection").style.display = "none";
                clearVisibleProgressLog();
                initProgressTracker();
                updateCurrentAgentCard({
                    agent_display_name: "恢复任务",
                    message: "检测到未完成任务，正在恢复进度...",
                    output_preview: { task_id: taskId },
                });
                var btn = document.getElementById("submitBtn");
                setSubmitLoading(true);
                setStopButtonsState(true, false, "强制停止");
                setBackToGenerationButtonState(true);
                var progress = Array.isArray(data.progress) ? data.progress : [];
                hydrateProgressSnapshot(progress);
                connectSSE(taskId, progress.length);
                return;
            }
            if (data.status === "done" && data.result) {
                finalizeGenerationDuration(data.duration_seconds);
                localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
                setUiStage("generation");
                addLogEntry("刷新后已恢复完成结果", "done");
                showResult(data.result, taskId);
                resetSubmitBtn(true);
                return;
            }
            finalizeGenerationDuration(data.duration_seconds);
            localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
            setUiStage("input");
            resetSubmitBtn(false);
        })
        .catch(function (err) {
            addLogEntry("恢复任务失败: " + err.message, "error");
            resetGenerationDurationDisplay();
            localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
            setUiStage("input");
            resetSubmitBtn(false);
        });
}

function forceStopTask() {
    if (!currentTaskId || !isGenerating) return;
    setStopButtonsState(true, true, "停止中...");

    fetch(API_PREFIX + "/stop/" + currentTaskId, { method: "POST" })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data && data.ok) {
                addLogEntry("已发送强制停止请求", "error");
                updateCurrentAgentCard({
                    agent_display_name: "任务终止中",
                    message: "已发送强制停止请求，等待当前节点中断...",
                    output_preview: { status: "cancelling" },
                });
                return;
            }
            throw new Error((data && data.error) || "停止请求失败");
        })
        .catch(function (err) {
            addLogEntry("强制停止失败: " + err.message, "error");
            setStopButtonsState(true, false, "强制停止");
        });
}

function hydrateProgressSnapshot(progressItems) {
    if (!Array.isArray(progressItems) || !progressItems.length) return;
    // 重放前先确保画布是干净的
    MatStage.reset();
    var maxStepReached = -1;
    var lastNormalized = null;
    progressItems.forEach(function (item) {
        if (typeof item === "string") {
            addLogEntry(item, "active");
            return;
        }
        addLogEntry(item.message || "", "active");
        var stepIdx = AGENT_STEPS.indexOf(item.agent);
        if (stepIdx > maxStepReached) maxStepReached = stepIdx;
        // 在回放过程中只触发画布增量更新（避免反复 toggle 接力条造成视觉抖动）
        MatStage.applyOutput(item);
        lastNormalized = item;
    });
    if (maxStepReached >= 0) {
        updateProgressBar(maxStepReached);
        updateStepTracker(maxStepReached);
    }
    // 最后基于"最新"的事件统一刷新接力条/状态卡
    if (lastNormalized) {
        updateCurrentAgentCard(lastNormalized);
    }
}

function initProgressTracker() {
    MatStage.init();
    renderGenerationStage({
        phaseIndex: -1,
        title: "准备生成",
        description: "提交后，6 位智能体会接力把这张地图画出来。",
        badge: "等待开始",
        progress: 0,
        state: "waiting",
    });
}

function updateStepTracker(stepIdx, done) {
    currentStepIndex = stepIdx;
    var agent = AGENT_STEPS[stepIdx] || "";
    var phaseIndex = getGenerationPhaseIndex(agent, stepIdx);
    renderGenerationPhases(done ? MAT_GENERATION_PHASES.length - 1 : phaseIndex, !!done);
}

function updateCurrentAgentCard(payload) {
    payload = payload || {};
    var state = deriveGenerationVisualState(payload);
    renderGenerationStage(state);

    if (state.state === "done") {
        MatStage.finalize();
    } else if (state.state === "error" || state.state === "cancelled") {
        MatStage.applyOutput(payload);
        MatStage.freezeWithError({
            freezeHint: state.state === "error" ? "执行失败" : "已停止",
        });
        MatStage.setStageHint(state.description || "");
    } else if (state.state === "recovering") {
        MatStage.applyOutput(payload);
        MatStage.setStageHint("正在接回未完成的任务…");
    } else if (state.state === "waiting") {
        MatStage.setStageHint(state.description || "等待开始");
    } else {
        MatStage.onAgentEvent(payload);
    }
}

function getGenerationPhaseIndex(agent, stepIdx) {
    if (agent && Object.prototype.hasOwnProperty.call(MAT_AGENT_PHASE_INDEX, agent)) {
        return MAT_AGENT_PHASE_INDEX[agent];
    }
    if (typeof stepIdx === "number" && stepIdx >= 0) {
        var ratio = stepIdx / Math.max(AGENT_STEPS.length - 1, 1);
        return Math.min(MAT_GENERATION_PHASES.length - 1, Math.floor(ratio * MAT_GENERATION_PHASES.length));
    }
    return -1;
}

function getGenerationProgressFromPayload(payload, phaseIndex) {
    var agentIdx = AGENT_STEPS.indexOf(payload.agent || "");
    if (agentIdx >= 0) {
        return Math.min(96, Math.max(8, Math.round(((agentIdx + 1) / AGENT_STEPS.length) * 96)));
    }
    if (phaseIndex >= 0) {
        return Math.min(96, Math.round(((phaseIndex + 1) / MAT_GENERATION_PHASES.length) * 92));
    }
    return 0;
}

function deriveGenerationVisualState(payload) {
    var output = payload.output_preview || {};
    var rawMessage = payload.message || "";
    var status = output.status || "";
    var state = "running";

    if (status === "waiting") state = "waiting";
    if (status === "error" || output.error || rawMessage.indexOf("生成出错") !== -1 || rawMessage.indexOf("执行失败") !== -1) state = "error";
    if (status === "cancelled" || status === "cancelling" || rawMessage.indexOf("强制停止") !== -1) state = "cancelled";
    if (payload.agent_display_name === "恢复任务") state = "recovering";
    if (payload.agent_display_name === "流程完成" || rawMessage.indexOf("教学地图已生成完成") !== -1) state = "done";

    if (state === "error") {
        return {
            phaseIndex: Math.max(getGenerationPhaseIndex("", currentStepIndex), 0),
            title: "生成遇到问题",
            description: rawMessage || "工作流执行失败，请稍后重试。",
            badge: "生成中断",
            progress: getDisplayedProgressValue(),
            state: "error",
        };
    }

    if (state === "cancelled") {
        return {
            phaseIndex: Math.max(getGenerationPhaseIndex("", currentStepIndex), 0),
            title: status === "cancelling" ? "正在停止生成" : "已停止生成",
            description: rawMessage || "任务已停止，可以返回输入界面调整后重新生成。",
            badge: status === "cancelling" ? "停止中" : "已停止",
            progress: getDisplayedProgressValue(),
            state: "cancelled",
        };
    }

    if (state === "done") {
        return {
            phaseIndex: MAT_GENERATION_PHASES.length - 1,
            title: "教学地图生成完成",
            description: "节点、连线与课堂推进顺序已经整理完毕。",
            badge: "生成完成",
            progress: 100,
            state: "done",
        };
    }

    if (state === "recovering") {
        return {
            phaseIndex: Math.max(getGenerationPhaseIndex("", currentStepIndex), 0),
            title: "正在恢复生成进度",
            description: "已找到未完成任务，正在接回实时生成过程。",
            badge: "恢复中",
            progress: getDisplayedProgressValue(),
            state: "recovering",
        };
    }

    var agentIdx = AGENT_STEPS.indexOf(payload.agent || "");
    var phaseIndex = getGenerationPhaseIndex(payload.agent || "", agentIdx);
    if (state === "waiting") {
        phaseIndex = -1;
    }
    var phase = MAT_GENERATION_PHASES[phaseIndex] || null;
    return {
        phaseIndex: phaseIndex,
        title: phase ? phase.title : "准备生成",
        description: phase ? phase.description : "提交后，教学地图会在这里逐步生长。",
        badge: phaseIndex >= 0 ? ("阶段 " + (phaseIndex + 1) + " / " + MAT_GENERATION_PHASES.length) : "等待开始",
        progress: getGenerationProgressFromPayload(payload, phaseIndex),
        state: state,
    };
}

function getDisplayedProgressValue() {
    var percent = document.getElementById("matGenerationPercent");
    if (!percent) return 0;
    var parsed = parseInt(percent.textContent, 10);
    return isFinite(parsed) ? parsed : 0;
}

function renderGenerationStage(state) {
    var progressBar = document.getElementById("progressBar");
    var percent = document.getElementById("matGenerationPercent");
    var progress = Math.max(0, Math.min(100, Math.round(Number(state.progress) || 0)));

    if (progressBar) progressBar.style.width = progress + "%";
    if (percent) percent.textContent = progress + "%";
}

// 旧 API 兼容保留：阶段列表已并入接力条 + 画布，此函数仅作 no-op
function renderGenerationPhases(activeIndex, done) {
    return;
}

function isMatPlainObject(value) {
    return !!value && typeof value === "object" && !Array.isArray(value);
}

function hasMatSummaryData(value) {
    if (value === null || value === undefined || value === "") return false;
    if (Array.isArray(value)) return value.length > 0;
    if (isMatPlainObject(value)) return Object.keys(value).length > 0;
    return true;
}

function matClipText(value, limit) {
    var text = value == null ? "" : String(value);
    text = text.replace(/\s+/g, " ").trim();
    if (!text) return "";
    var max = limit || 120;
    return text.length > max ? text.slice(0, max) + "..." : text;
}

function matQuestionText(item) {
    if (!item) return "";
    if (typeof item === "string") return matClipText(item, 96);
    if (!isMatPlainObject(item)) return matClipText(String(item), 96);
    return matClipText(
        item.content || item.question || item.title || item.name || item.original_text || item.id || "",
        96
    );
}

function matCountLabel(count, unit) {
    return '<span class="mat-summary-count">' + escapeHtml(String(count)) + '</span>' + unit;
}

function renderMatSummaryEmpty(text) {
    return '<div class="mat-summary-empty">' + escapeHtml(text) + '</div>';
}

function renderMatSummaryList(items) {
    if (!items || !items.length) return "";
    return '<ul class="mat-summary-list">' + items.map(function (item) {
        return '<li>' + item + '</li>';
    }).join("") + '</ul>';
}

function renderMatSummaryPills(items) {
    if (!items || !items.length) return "";
    return '<div class="mat-summary-pills">' + items.map(function (item) {
        return '<span>' + escapeHtml(matClipText(item, 28)) + '</span>';
    }).join("") + '</div>';
}

function extractMatArray(value) {
    if (Array.isArray(value)) return value;
    if (!isMatPlainObject(value)) return [];
    var keys = ["items", "questions", "nodes", "edges", "main_question_chain", "teaching_objectives", "sub_goals", "knowledge_points", "feedback", "issues", "results"];
    for (var i = 0; i < keys.length; i++) {
        if (Array.isArray(value[keys[i]])) return value[keys[i]];
    }
    return [];
}

function summarizeMatQuestions(label, value, unit) {
    var arr = extractMatArray(value);
    if (!arr.length) return "";
    var samples = arr.slice(0, 3).map(function (item) {
        return escapeHtml(matQuestionText(item));
    }).filter(Boolean);
    var html = label + "：" + matCountLabel(arr.length, unit || "个");
    if (samples.length) {
        html += renderMatSummaryPills(samples);
    }
    return html;
}

function summarizeMatTeachingMap(value) {
    if (!isMatPlainObject(value)) return "";
    var nodes = Array.isArray(value.nodes) ? value.nodes : [];
    var edges = Array.isArray(value.edges) ? value.edges : [];
    var counts = { main: 0, variant: 0, scaffold: 0 };
    nodes.forEach(function (node) {
        var type = node && (node.question_type || node.type);
        if (counts[type] !== undefined) counts[type] += 1;
    });
    var parts = [
        "问题节点 " + matCountLabel(nodes.length, "个"),
        "连接关系 " + matCountLabel(edges.length, "条"),
    ];
    var typeParts = [];
    if (counts.main) typeParts.push("主干 " + counts.main);
    if (counts.variant) typeParts.push("变式 " + counts.variant);
    if (counts.scaffold) typeParts.push("支架 " + counts.scaffold);
    if (typeParts.length) parts.push("其中 " + escapeHtml(typeParts.join("、")));
    return "已整合教学地图：" + parts.join("，") + "。";
}

function summarizeMatAnalysisResult(value) {
    if (!isMatPlainObject(value)) return "";
    var items = [];
    var goals = value.teaching_objectives || value.sub_goals || value.learning_goals || value.goals;
    var knowledge = value.knowledge_points || value.core_knowledge_points || value.knowledge_graph;
    var profile = value.student_profile || value.student_analysis || value.learner_profile;
    var focus = value.teaching_focus || value.key_points || value.difficulty_analysis;
    if (Array.isArray(goals) && goals.length) items.push("拆解出 " + matCountLabel(goals.length, "个") + "可观察的学习目标");
    if (Array.isArray(knowledge) && knowledge.length) items.push("提取 " + matCountLabel(knowledge.length, "个") + "核心知识点" + renderMatSummaryPills(knowledge.slice(0, 5).map(matQuestionText)));
    if (profile) items.push("形成学情画像：" + escapeHtml(matClipText(profile, 90)));
    if (focus) items.push("识别教学重点/难点：" + escapeHtml(matClipText(focus, 90)));
    if (!items.length) items.push("已完成学情、目标和知识结构的综合解析。");
    return renderMatSummaryList(items);
}

function summarizeMatValidation(value) {
    var arr = extractMatArray(value);
    if (!arr.length && isMatPlainObject(value)) {
        arr = Object.keys(value).map(function (key) { return value[key]; });
    }
    if (!arr.length) return "";
    var passed = 0;
    var failed = 0;
    var samples = [];
    arr.forEach(function (item) {
        var text = matQuestionText(item);
        var raw = JSON.stringify(item || "");
        if (/未通过|失败|fail|false/i.test(raw)) failed += 1;
        else if (/通过|pass|true/i.test(raw)) passed += 1;
        if (text && samples.length < 3) samples.push(escapeHtml(text));
    });
    var summary = "完成 " + matCountLabel(arr.length, "项") + "校验";
    if (passed || failed) summary += "：通过 " + passed + " 项，需调整 " + failed + " 项";
    if (samples.length) summary += renderMatSummaryPills(samples);
    return summary;
}

function summarizeMatStatus(value) {
    var status = String(value || "");
    var labels = {
        waiting: "等待工作流开始执行。",
        error: "执行过程中出现异常，请查看上方提示。",
        cancelled: "任务已停止。",
        cancelling: "正在停止任务，请稍候。",
        done: "本步已完成。",
    };
    return labels[status] || ("当前状态：" + escapeHtml(status));
}

function summarizeMatObjectGeneric(value) {
    if (!isMatPlainObject(value)) return "";
    var keys = Object.keys(value).filter(function (key) {
        return key !== "progress_messages" && hasMatSummaryData(value[key]);
    });
    if (!keys.length) return "";
    var items = keys.slice(0, 4).map(function (key) {
        return summarizeMatValue(key, value[key]);
    }).filter(Boolean);
    if (items.length) return renderMatSummaryList(items);
    return "已形成 " + matCountLabel(keys.length, "项") + "结构化结果，可供后续步骤继续使用。";
}

function summarizeMatValue(key, value) {
    var label = MAT_FIELD_LABELS[key] || key;
    if (!hasMatSummaryData(value)) return "";

    if (key === "status") return summarizeMatStatus(value);
    if (key === "error") return "异常信息：" + escapeHtml(matClipText(value, 160));
    if (key === "model_id") return "使用模型：" + escapeHtml(matClipText(value, 80));
    if (key === "temperature") return "生成随机性参数：" + escapeHtml(String(value));
    if (key === "teaching_goals" || key === "student_profile" || key === "difficulty_analysis" || key === "attachment") {
        return label + "：" + escapeHtml(matClipText(value, key === "attachment" ? 180 : 140));
    }
    if (key === "subject" || key === "grade" || key === "language_style") {
        return label + "：" + escapeHtml(matClipText(value, 80));
    }
    if (key === "analysis_result") return summarizeMatAnalysisResult(value);
    if (key === "teaching_map") return summarizeMatTeachingMap(value);
    if (key === "main_questions") return summarizeMatQuestions("已形成主干问题", value, "个");
    if (key === "variant_questions") return summarizeMatQuestions("已生成变式问题", value, "个");
    if (key === "scaffold_questions") return summarizeMatQuestions("已生成支架问题", value, "个");
    if (key === "map_construction_logic") return summarizeMatQuestions("规划出主干问题链", value, "个环节");
    if (key === "variant_question_plan") return summarizeMatQuestions("规划变式问题任务", value, "项");
    if (key === "scaffold_question_plan") return summarizeMatQuestions("规划支架问题任务", value, "项");
    if (key.indexOf("validation") !== -1 || key.indexOf("feedback") !== -1 || key === "validation_results") return summarizeMatValidation(value);
    if (key === "nodes") return "教学地图包含问题节点：" + matCountLabel(Number(value) || (Array.isArray(value) ? value.length : 0), "个");
    if (key === "edges") return "教学地图包含连接关系：" + matCountLabel(Number(value) || (Array.isArray(value) ? value.length : 0), "条");
    if (Array.isArray(value)) {
        if (!value.length) return "";
        var sample = value.slice(0, 3).map(matQuestionText).filter(Boolean);
        var html = label + "：" + matCountLabel(value.length, "项");
        if (sample.length) html += renderMatSummaryPills(sample);
        return html;
    }
    if (isMatPlainObject(value)) return label + "：" + summarizeMatObjectGeneric(value);
    return label + "：" + escapeHtml(matClipText(value, 140));
}

function renderTeacherSummarySection(data, emptyText, preferredKeys) {
    if (!hasMatSummaryData(data)) return renderMatSummaryEmpty(emptyText);
    if (typeof data === "string") return renderMatSummaryList([escapeHtml(matClipText(data, 180))]);
    if (!isMatPlainObject(data)) return renderMatSummaryList([escapeHtml(matClipText(String(data), 180))]);

    var keys = [];
    (preferredKeys || []).forEach(function (key) {
        if (Object.prototype.hasOwnProperty.call(data, key) && keys.indexOf(key) === -1) keys.push(key);
    });
    Object.keys(data).forEach(function (key) {
        if (key !== "progress_messages" && keys.indexOf(key) === -1) keys.push(key);
    });

    var items = keys.map(function (key) {
        return summarizeMatValue(key, data[key]);
    }).filter(Boolean);

    if (!items.length) return renderMatSummaryEmpty(emptyText);
    return renderMatSummaryList(items);
}

function renderTeacherInputSummary(data) {
    return renderTeacherSummarySection(data, "本步无需额外输入，会接续上一步结果。", [
        "subject", "grade", "teaching_goals", "student_profile", "difficulty_analysis",
        "language_style", "attachment", "analysis_result", "map_construction_logic",
        "main_questions", "variant_questions", "scaffold_questions", "validation_results",
    ]);
}

function renderTeacherOutputSummary(data) {
    return renderTeacherSummarySection(data, "等待本步执行完成后显示产出。", [
        "status", "error", "analysis_result", "map_construction_logic", "main_questions",
        "variant_questions", "scaffold_questions", "validation_results", "teaching_map",
        "nodes", "edges", "priorities", "priority_assignments",
    ]);
}

function renderTeacherIoSummary(inputData, outputData, payload) {
    return {
        input: renderTeacherInputSummary(inputData),
        output: renderTeacherOutputSummary(outputData || (payload ? payload.output_preview : null)),
    };
}

// ---------------------------------------------------------------------------
// Show result (graph + text + logs)
// ---------------------------------------------------------------------------
function showResult(result, taskId) {
    currentResult = result;
    if (taskId) currentTaskId = taskId;
    setUiStage("generation");
    document.getElementById("viewTabs").style.display = "flex";
    document.querySelectorAll(".mat-view-tab").forEach(function (b) { b.classList.remove("active"); });
    document.querySelector('.mat-view-tab[data-view="graph"]').classList.add("active");
    document.getElementById("graphSection").style.display = "block";
    document.getElementById("textSection").style.display = "none";
    document.getElementById("logsSection").style.display = "none";
    document.getElementById("detailSection").style.display = "none";
    renderGraph(result);
    renderTextView(result);
    showNavEntryButton(taskId);
}

function showNavEntryButton(taskId) {
    var bar = document.getElementById("navEntryBar");
    var btn = document.getElementById("startNavBtn");
    if (!bar || !btn) return;
    var tid = taskId || currentTaskId;
    if (tid) {
        btn.href = "/app/teaching-nav/" + tid;
        bar.style.display = "flex";
    } else {
        bar.style.display = "none";
    }
}

function hideNavEntryBar() {
    var bar = document.getElementById("navEntryBar");
    if (bar) bar.style.display = "none";
}

// ---------------------------------------------------------------------------
// Agent Logs View
// ---------------------------------------------------------------------------
function loadAgentLogs(taskId) {
    var container = document.getElementById("logsContent");
    container.innerHTML = '<p class="mat-logs-loading">加载日志中...</p>';

    fetch(API_PREFIX + "/logs/" + taskId)
        .then(function (res) { return res.json(); })
        .then(function (logs) {
            if (!logs || !logs.length) {
                container.innerHTML = '<p class="mat-logs-empty">暂无日志记录</p>';
                return;
            }
            var html = '<div class="mat-logs-summary"><p>共 <strong>' + logs.length + '</strong> 个Agent执行记录</p></div>';
            logs.forEach(function (log) {
                var output = log.output || {};
                var inputData = output.input_preview || null;
                var outputData = output.output || output;
                if (outputData && outputData.input_preview) {
                    outputData = Object.assign({}, outputData);
                    delete outputData.input_preview;
                }
                html += '<div class="mat-log-block">';
                html += '<div class="mat-log-block-header">';
                html += '<span class="mat-log-step">步骤 ' + log.step_number + '</span>';
                html += '<span class="mat-log-agent-name">' + log.agent_name + '</span>';
                html += '<span class="mat-log-time">' + log.created_at + '</span>';
                html += '<button class="mat-log-toggle" onclick="toggleLogDetail(this)">展开</button>';
                html += '</div>';
                html += '<div class="mat-log-block-body" style="display:none;">';
                html += '<div class="mat-log-io-grid">';
                html += '<div class="mat-log-io-panel">';
                html += '<div class="mat-log-io-head"><span class="mat-io-icon mat-io-in">参考</span>本步参考</div>';
                html += '<div class="mat-log-io-body">' + renderTeacherInputSummary(inputData) + '</div>';
                html += '</div>';
                html += '<div class="mat-log-io-panel">';
                html += '<div class="mat-log-io-head"><span class="mat-io-icon mat-io-out">产出</span>本步产出</div>';
                html += '<div class="mat-log-io-body">' + renderTeacherOutputSummary(outputData) + '</div>';
                html += '</div>';
                html += '</div></div></div>';
            });
            container.innerHTML = html;
        })
        .catch(function (err) {
            container.innerHTML = '<p class="mat-logs-error">加载日志失败: ' + err.message + '</p>';
        });
}

function toggleLogDetail(btn) {
    var body = btn.parentElement.nextElementSibling;
    if (body.style.display === "none") { body.style.display = "block"; btn.textContent = "收起"; }
    else { body.style.display = "none"; btn.textContent = "展开"; }
}

function escapeHtml(text) {
    var div = document.createElement("div");
    div.innerText = text;
    return div.innerHTML;
}

function renderMarkdownHtml(text) {
    var source = text == null ? "" : String(text);
    if (!source) return "";

    if (typeof marked !== "undefined" && marked && typeof marked.parse === "function") {
        if (!markdownOptionsApplied && typeof marked.setOptions === "function") {
            marked.setOptions({ gfm: true, breaks: true });
            markdownOptionsApplied = true;
        }
        var rendered = marked.parse(source);
        if (typeof DOMPurify !== "undefined" && DOMPurify && typeof DOMPurify.sanitize === "function") {
            return DOMPurify.sanitize(rendered, { USE_PROFILES: { html: true } });
        }
        return escapeHtml(source).replace(/\n/g, "<br>");
    }

    return escapeHtml(source).replace(/\n/g, "<br>");
}

// ---------------------------------------------------------------------------
// Text view rendering
// ---------------------------------------------------------------------------
function renderTextView(teachingMap) {
    var container = document.getElementById("textContent");
    var nodes = teachingMap.nodes || [];
    var edges = teachingMap.edges || [];

    var mainNodes = nodes.filter(function (n) { return n.question_type === "main"; });
    var variantNodes = nodes.filter(function (n) { return n.question_type === "variant"; });
    var scaffoldNodes = nodes.filter(function (n) { return n.question_type === "scaffold"; });
    var mainOrder = orderMainNodes(mainNodes, edges);

    var html = '<div class="mat-text-summary">';
    html += '<p>共 <strong>' + nodes.length + '</strong> 个问题节点（主干 ' + mainNodes.length + ' 个、变式 ' + variantNodes.length + ' 个、支架 ' + scaffoldNodes.length + ' 个），<strong>' + edges.length + '</strong> 条连接关系</p>';
    html += '</div>';

    mainOrder.forEach(function (mainNode, idx) {
        html += '<div class="mat-text-block mat-text-main">';
        html += '<div class="mat-text-block-header mat-main-header">';
        html += '<span class="mat-text-num">' + (idx + 1) + '</span>';
        html += '<span class="mat-text-tag mat-tag-main">主干问题</span>';
        html += '<span class="mat-text-id">' + escapeHtml(String(mainNode.id || "")) + '</span>';
        html += '</div>';
        html += '<div class="mat-text-block-body">';
        html += renderVisualAidBlock(mainNode);
        html += '<div class="mat-text-question mat-markdown-content">' + renderMarkdownHtml(mainNode.content || "") + '</div>';
        html += renderMeta(mainNode);
        html += renderCommentaryBlock(mainNode);
        html += '</div>';

        var relatedVariants = variantNodes.filter(function (v) {
            return (v.main_id || v.parent_id) === mainNode.id;
        });
        if (relatedVariants.length > 0) {
            html += '<div class="mat-text-sub-group">';
            html += '<div class="mat-text-sub-label mat-variant-label">变式问题</div>';
            relatedVariants.forEach(function (v) {
                html += '<div class="mat-text-block mat-text-variant">';
                html += '<div class="mat-text-block-header mat-variant-header">';
                html += '<span class="mat-text-tag mat-tag-variant">变式</span>';
                html += '<span class="mat-text-id">' + escapeHtml(String(v.id || "")) + '</span>';
                if (v.variation_type) html += '<span class="mat-text-vtype">' + escapeHtml(String(v.variation_type)) + '</span>';
                html += '</div>';
                html += '<div class="mat-text-block-body">';
                html += renderVisualAidBlock(v);
                html += '<div class="mat-text-question mat-markdown-content">' + renderMarkdownHtml(v.content || "") + '</div>';
                html += renderMeta(v);
                html += renderCommentaryBlock(v);
                html += '</div></div>';
            });
            html += '</div>';
        }

        if (idx < mainOrder.length - 1) {
            var nextMain = mainOrder[idx + 1];
            var relatedScaffolds = scaffoldNodes.filter(function (s) {
                var fromId = s.from_id || s.from_main_id;
                var toId = s.to_id || s.to_main_id;
                return fromId === mainNode.id || toId === nextMain.id;
            });
            if (relatedScaffolds.length > 0) {
                html += '<div class="mat-text-sub-group">';
                html += '<div class="mat-text-sub-label mat-scaffold-label">支架问题（过渡到下一主干）</div>';
                relatedScaffolds.forEach(function (s) {
                    html += '<div class="mat-text-block mat-text-scaffold">';
                    html += '<div class="mat-text-block-header mat-scaffold-header">';
                    html += '<span class="mat-text-tag mat-tag-scaffold">支架</span>';
                    html += '<span class="mat-text-id">' + escapeHtml(String(s.id || "")) + '</span>';
                    html += '</div>';
                    html += '<div class="mat-text-block-body">';
                    html += renderVisualAidBlock(s);
                    html += '<div class="mat-text-question mat-markdown-content">' + renderMarkdownHtml(s.content || "") + '</div>';
                    html += renderMeta(s);
                    html += renderCommentaryBlock(s);
                    if (s.bridge_function) html += '<div class="mat-text-bridge mat-markdown-content"><strong>桥梁功能：</strong>' + renderMarkdownHtml(s.bridge_function) + '</div>';
                    html += '</div></div>';
                });
                html += '</div>';
            }
            html += '<div class="mat-text-arrow">&#8595;</div>';
        }
        html += '</div>';
    });

    container.innerHTML = html;
}

function renderMeta(node) {
    var html = '<div class="mat-text-meta">';
    var designIntent = node.design_intent || node.design_rationale || "";
    if (node.knowledge_points && node.knowledge_points.length) {
        html += '<span>知识点：' + escapeHtml(node.knowledge_points.join("、")) + '</span>';
    }
    var cl = node.cognitive_level || node.bloom_level || "";
    var clLabel = COGNITIVE_LABELS[cl] || cl;
    if (clLabel) html += '<span>认知层次：' + escapeHtml(String(clLabel)) + '</span>';
    if (node.difficulty !== undefined) html += '<span>难度：' + escapeHtml(String(node.difficulty)) + '</span>';
    if (designIntent) html += '<span>设计意图：' + escapeHtml(String(designIntent)) + '</span>';
    html += '</div>';
    return html;
}

function getCommentary(node) {
    return (node && (node.lesson_presentation_script || node.commentary || node.Commentary)) || "";
}

function renderCommentaryBlock(node) {
    var commentary = getCommentary(node);
    if (!commentary) return "";
    return '<div class="mat-text-commentary"><div class="mat-text-commentary-title">说课稿</div><div class="mat-text-commentary-body mat-markdown-content">' + renderMarkdownHtml(commentary) + '</div></div>';
}

// 交互动画「桌面 4:3 设计视口」尺寸：iframe 以此渲染保持桌面横排布局，
// 再用 transform 等比缩放塞进定宽 4:3 盒子，确保整幅动画完整可见。
var VA_DESIGN_W = 960;
var VA_DESIGN_H = 720;

function fitInteractiveFrame(frameEl) {
    if (!frameEl) return;
    var box = frameEl.closest(".mat-visual-aid-frame-box");
    if (!box) return;
    var pw = box.clientWidth;
    var ph = box.clientHeight;
    if (!pw || !ph) return;
    var scale = Math.min(pw / VA_DESIGN_W, ph / VA_DESIGN_H);
    var x = (pw - VA_DESIGN_W * scale) / 2;
    var y = (ph - VA_DESIGN_H * scale) / 2;
    frameEl.style.setProperty("--va-w", VA_DESIGN_W + "px");
    frameEl.style.setProperty("--va-h", VA_DESIGN_H + "px");
    frameEl.style.setProperty("--va-scale", scale);
    frameEl.style.setProperty("--va-x", x + "px");
    frameEl.style.setProperty("--va-y", y + "px");
}
window.fitInteractiveFrame = fitInteractiveFrame;

function fitAllInteractiveFrames() {
    var frames = document.querySelectorAll(".mat-visual-aid-frame");
    for (var i = 0; i < frames.length; i++) {
        fitInteractiveFrame(frames[i]);
    }
}
window.fitAllInteractiveFrames = fitAllInteractiveFrames;

window.addEventListener("resize", fitAllInteractiveFrames);

function renderVisualAidBlock(node) {
    var interactiveHtml = node.visual_aid_html || "";
    var urls = node.visual_aid_urls || [];
    var prompt = node.visual_aid_prompt || "";
    var vaType = node.visual_aid_type || "";
    var nodeId = node.id || "";

    if (vaType === "none" && !urls.length && !interactiveHtml) return "";

    var html = '<div class="mat-visual-aid-section" data-node-id="' + escapeHtml(nodeId) + '">';

    if (interactiveHtml) {
        html += '<div class="mat-visual-aid-preview mat-visual-aid-interactive-preview">';
        html += '<div class="mat-visual-aid-frame-box">';
        html += '<iframe class="mat-visual-aid-frame" title="交互可视化" sandbox="allow-scripts" loading="lazy" referrerpolicy="no-referrer" onload="window.fitInteractiveFrame&&fitInteractiveFrame(this)" srcdoc="' + escapeHtml(interactiveHtml) + '"></iframe>';
        html += '</div>';
        html += '<div class="mat-visual-aid-actions">';
        html += "<button type=\"button\" class=\"mat-visual-aid-btn\" onclick=\"openTextViewInteractiveLightbox(this.closest('.mat-visual-aid-section'))\">";
        html += '<svg viewBox="0 0 20 20" fill="currentColor" width="14" height="14"><path d="M5 8a1 1 0 011-1h3V4a1 1 0 112 0v3h3a1 1 0 110 2h-3v3a1 1 0 11-2 0V9H6a1 1 0 01-1-1z"/><path fill-rule="evenodd" d="M8 16A8 8 0 108 0a8 8 0 000 16zm0-2A6 6 0 108 2a6 6 0 000 12z" clip-rule="evenodd"/></svg>';
        html += '放大交互';
        html += '</button>';
        html += '</div>';
        html += '</div>';
    } else if (urls.length > 0 && urls[0]) {
        html += '<div class="mat-visual-aid-preview">';
        html += '<img src="' + escapeHtml(urls[0]) + '" alt="配图" class="mat-visual-aid-thumb" onclick="openTextViewLightbox(this.src)">';
        html += '<div class="mat-visual-aid-actions">';
        html += '<label class="mat-visual-aid-btn mat-visual-aid-replace">';
        html += '<input type="file" accept="image/*" style="display:none" onchange="handleVisualAidUpload(this, \'' + escapeHtml(nodeId) + '\')">';
        html += '<svg viewBox="0 0 20 20" fill="currentColor" width="14" height="14"><path d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z"/></svg>';
        html += '替换配图';
        html += '</label>';
        html += '<button type="button" class="mat-visual-aid-btn mat-visual-aid-delete" onclick="handleVisualAidDelete(\'' + escapeHtml(nodeId) + '\', this)">';
        html += '<svg viewBox="0 0 20 20" fill="currentColor" width="14" height="14"><path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd"/></svg>';
        html += '删除';
        html += '</button>';
        html += '</div>';
        html += '</div>';
    } else if (prompt) {
        html += '<div class="mat-visual-aid-placeholder">';
        html += '<div class="mat-visual-aid-prompt-text">';
        html += '<svg viewBox="0 0 20 20" fill="currentColor" width="16" height="16"><path fill-rule="evenodd" d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z" clip-rule="evenodd"/></svg>';
        html += '<span>' + escapeHtml(prompt) + '</span>';
        html += '</div>';
        html += '</div>';
    } else {
        html += '<div class="mat-visual-aid-placeholder">';
        html += '<div class="mat-visual-aid-prompt-text">暂无可视化材料</div>';
        html += '</div>';
    }

    html += '</div>';
    return html;
}

function handleVisualAidUpload(inputEl, nodeId) {
    var file = inputEl.files && inputEl.files[0];
    if (!file) return;
    if (!currentTaskId) { alert("当前无活动任务"); return; }
    if (file.size > 5 * 1024 * 1024) { alert("文件过大，最大支持 5MB"); return; }

    var formData = new FormData();
    formData.append("task_id", currentTaskId);
    formData.append("node_id", nodeId);
    formData.append("image", file);

    var section = inputEl.closest(".mat-visual-aid-section");
    if (section) section.style.opacity = "0.5";

    fetch(API_PREFIX + "/node-image/upload", { method: "POST", body: formData })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.url) {
                updateNodeVisualAidInResult(nodeId, data.url);
                if (currentResult) renderTextView(currentResult);
            } else {
                alert(data.error || "上传失败");
                if (section) section.style.opacity = "1";
            }
        })
        .catch(function () {
            alert("上传出错");
            if (section) section.style.opacity = "1";
        });
}

function handleVisualAidDelete(nodeId, btnEl) {
    if (!currentTaskId) return;
    if (!confirm("确定删除该节点的配图？")) return;

    var section = btnEl.closest(".mat-visual-aid-section");
    if (section) section.style.opacity = "0.5";

    fetch(API_PREFIX + "/node-image/" + currentTaskId + "/" + nodeId, { method: "DELETE" })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            updateNodeVisualAidInResult(nodeId, null);
            if (currentResult) renderTextView(currentResult);
        })
        .catch(function () {
            alert("删除出错");
            if (section) section.style.opacity = "1";
        });
}

function updateNodeVisualAidInResult(nodeId, url) {
    if (!currentResult || !currentResult.nodes) return;
    for (var i = 0; i < currentResult.nodes.length; i++) {
        if (currentResult.nodes[i].id === nodeId) {
            currentResult.nodes[i].visual_aid_urls = url ? [url] : [];
            break;
        }
    }
}

function openTextViewLightbox(src) {
    var overlay = document.getElementById("matTextViewLightbox");
    if (!overlay) {
        overlay = document.createElement("div");
        overlay.id = "matTextViewLightbox";
        overlay.className = "mat-lightbox-overlay";
        overlay.innerHTML = '<div class="mat-lightbox-backdrop"></div><div class="mat-lightbox-content"><img class="mat-lightbox-img" src="" alt="放大查看"><button class="mat-lightbox-close" type="button">&times;</button></div>';
        document.body.appendChild(overlay);
        overlay.querySelector(".mat-lightbox-backdrop").addEventListener("click", function () { overlay.style.display = "none"; });
        overlay.querySelector(".mat-lightbox-close").addEventListener("click", function () { overlay.style.display = "none"; });
    }
    overlay.querySelector(".mat-lightbox-img").src = src;
    overlay.style.display = "flex";
}

function openTextViewInteractiveLightbox(sectionEl) {
    if (!sectionEl) return;
    var sourceFrame = sectionEl.querySelector(".mat-visual-aid-frame");
    if (!sourceFrame) return;
    var overlay = document.getElementById("matTextViewInteractiveLightbox");
    if (!overlay) {
        overlay = document.createElement("div");
        overlay.id = "matTextViewInteractiveLightbox";
        overlay.className = "mat-lightbox-overlay";
        overlay.innerHTML = '<div class="mat-lightbox-backdrop"></div><div class="mat-lightbox-content mat-lightbox-interactive-content"><iframe class="mat-lightbox-frame" title="交互可视化放大" sandbox="allow-scripts" referrerpolicy="no-referrer"></iframe><button class="mat-lightbox-close" type="button">&times;</button></div>';
        document.body.appendChild(overlay);
        overlay.querySelector(".mat-lightbox-backdrop").addEventListener("click", function () {
            overlay.style.display = "none";
            overlay.querySelector(".mat-lightbox-frame").removeAttribute("srcdoc");
        });
        overlay.querySelector(".mat-lightbox-close").addEventListener("click", function () {
            overlay.style.display = "none";
            overlay.querySelector(".mat-lightbox-frame").removeAttribute("srcdoc");
        });
    }
    overlay.querySelector(".mat-lightbox-frame").srcdoc = sourceFrame.getAttribute("srcdoc") || "";
    overlay.style.display = "flex";
}

function orderMainNodes(mainNodes, edges) {
    if (mainNodes.length <= 1) return mainNodes;
    var seqEdges = edges.filter(function (e) { return e.relation === "sequence"; });
    var mainIds = new Set(mainNodes.map(function (n) { return n.id; }));
    var adj = {};
    var inDeg = {};
    mainIds.forEach(function (id) { adj[id] = []; inDeg[id] = 0; });
    seqEdges.forEach(function (e) {
        if (mainIds.has(e.source) && mainIds.has(e.target)) {
            adj[e.source].push(e.target);
            inDeg[e.target] = (inDeg[e.target] || 0) + 1;
        }
    });
    var queue = [];
    mainIds.forEach(function (id) { if (!inDeg[id]) queue.push(id); });
    var ordered = [];
    while (queue.length) {
        var cur = queue.shift();
        ordered.push(cur);
        (adj[cur] || []).forEach(function (next) { inDeg[next]--; if (inDeg[next] === 0) queue.push(next); });
    }
    var byId = {};
    mainNodes.forEach(function (n) { byId[n.id] = n; });
    var result = ordered.filter(function (id) { return byId[id]; }).map(function (id) { return byId[id]; });
    mainNodes.forEach(function (n) { if (ordered.indexOf(n.id) === -1) result.push(n); });
    return result;
}

// ---------------------------------------------------------------------------
// History
// ---------------------------------------------------------------------------
function closeAllMoreMenus() {
    document.querySelectorAll(".mat-more-menu.is-open").forEach(function (m) {
        m.classList.remove("is-open");
    });
}

function bindHistoryListEvents() {
    if (historyEventsBound) return;
    var list = document.getElementById("historyList");
    if (!list) return;

    document.addEventListener("click", function (e) {
        if (!e.target.closest(".mat-history-more-wrap")) closeAllMoreMenus();
    });

    list.addEventListener("click", function (event) {
        var moreBtn = event.target.closest(".mat-btn-more");
        if (moreBtn) {
            event.stopPropagation();
            var menu = moreBtn.nextElementSibling;
            var isOpen = menu && menu.classList.contains("is-open");
            closeAllMoreMenus();
            if (menu && !isOpen) {
                menu.classList.remove("mat-more-menu--below");
                menu.classList.add("is-open");
                var btnRect = moreBtn.getBoundingClientRect();
                var listEl = document.getElementById("historyList");
                var listTop = listEl ? listEl.getBoundingClientRect().top : 0;
                var menuHeight = menu.offsetHeight || 150;
                if (btnRect.top - listTop < menuHeight + 12) {
                    menu.classList.add("mat-more-menu--below");
                }
            }
            return;
        }

        var btn = event.target.closest("button");
        if (!btn) return;
        var item = btn.closest(".mat-history-item");
        if (!item) return;
        var recordId = item.getAttribute("data-id");
        if (!recordId) return;

        closeAllMoreMenus();

        if (btn.classList.contains("mat-btn-view")) {
            loadHistoryItem(recordId);
            return;
        }
        if (btn.classList.contains("mat-btn-export")) {
            exportHistoryItem(recordId, event, btn);
            return;
        }
        if (btn.classList.contains("mat-btn-input")) {
            toggleHistoryInput(recordId, btn, event);
            return;
        }
        if (btn.classList.contains("mat-btn-logs")) {
            loadHistoryLogs(recordId, event);
            return;
        }
        if (btn.classList.contains("mat-btn-delete")) {
            deleteHistoryItem(recordId, event);
        }
    });
    historyEventsBound = true;
}

function loadHistory() {
    bindHistoryListEvents();
    var container = document.getElementById("historyList");
    if (!container) return;
    container.innerHTML = '<p class="mat-history-empty">加载中...</p>';

    fetch(API_PREFIX + "/history")
        .then(function (res) {
            return res.json().then(function (data) {
                return { ok: res.ok, status: res.status, data: data };
            });
        })
        .then(function (payload) {
            var list = payload.data;
            if (!payload.ok) {
                var errMsg = (list && list.msg) ? list.msg : "历史记录加载失败（HTTP " + payload.status + "）";
                container.innerHTML = '<p class="mat-history-empty mat-history-error">' + escapeHtml(errMsg) + "</p>";
                return;
            }
            if (!Array.isArray(list)) {
                container.innerHTML = '<p class="mat-history-empty mat-history-error">历史接口返回格式异常</p>';
                return;
            }
            if (!list.length) {
                container.innerHTML = '<div class="mat-history-empty">'
                    + '<svg class="mat-history-empty-illustration" viewBox="0 0 64 64" fill="none" width="48" height="48">'
                    + '<rect x="12" y="8" width="40" height="48" rx="6" stroke="currentColor" stroke-width="2"/>'
                    + '<line x1="22" y1="22" x2="42" y2="22" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
                    + '<line x1="22" y1="30" x2="38" y2="30" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
                    + '<line x1="22" y1="38" x2="34" y2="38" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
                    + '</svg>'
                    + '<p>暂无历史记录</p>'
                    + '<p class="mat-history-empty-hint">生成教学地图后，记录将出现在这里</p>'
                    + '</div>';
                return;
            }
            var html = "";
            list.forEach(function (item) {
                var goals = (item.teaching_goals || "").substring(0, 60);
                var safeGoals = escapeHtml(goals + (goals.length >= 60 ? "..." : ""));
                var modelDisplayName = escapeHtml(item.model_display_name || "未知模型");
                var durationSeconds = Number(item.duration_seconds);
                var hasDuration = isFinite(durationSeconds) && durationSeconds >= 0;
                var subjectAttr = escapeHtml(item.subject || "");
                html += '<div class="mat-history-item" data-id="' + item.id + '" data-subject-color="' + subjectAttr + '">';
                html += '<div class="mat-history-item-header">';
                html += '<span class="mat-history-subject">' + escapeHtml(item.subject || "") + ' · ' + escapeHtml(item.grade || "") + '</span>';
                html += '<span class="mat-history-time">' + escapeHtml(item.created_at || "") + '</span>';
                html += '</div>';
                html += '<div class="mat-history-goals">' + safeGoals + '</div>';
                html += '<div class="mat-history-model">生成模型：' + modelDisplayName;
                if (hasDuration) html += ' · 用时 ' + formatDurationClock(durationSeconds);
                html += '</div>';
                html += '<div class="mat-history-actions">';
                html += '<button class="mat-btn-sm mat-btn-view" type="button">查看</button>';
                html += '<a class="mat-btn-sm mat-btn-nav" href="/app/teaching-nav/' + item.id + '">导航</a>';
                html += '<div class="mat-history-more-wrap">';
                html += '<button class="mat-btn-more" type="button" aria-label="更多操作">&#8943;</button>';
                html += '<div class="mat-more-menu">';
                html += '<button class="mat-btn-sm mat-btn-export" type="button">导出教案</button>';
                html += '<button class="mat-btn-sm mat-btn-input" type="button">查看输入</button>';
                html += '<button class="mat-btn-sm mat-btn-logs" type="button">查看日志</button>';
                html += '<button class="mat-btn-sm mat-btn-delete" type="button">删除记录</button>';
                html += '</div></div>';
                html += '</div>';
                html += '<div class="mat-history-input-detail" id="historyInputDetail-' + item.id + '" style="display:none;"></div>';
                html += '</div>';
            });
            container.innerHTML = html;
            refreshLoadLastInputAvailability();
        })
        .catch(function (err) {
            container.innerHTML = '<p class="mat-history-empty mat-history-error">历史记录加载失败：' + escapeHtml(String(err && err.message ? err.message : err)) + "</p>";
            refreshLoadLastInputAvailability();
        });
}

function toggleHistoryInput(recordId, btn, event) {
    if (event && typeof event.stopPropagation === "function") event.stopPropagation();
    var detail = document.getElementById("historyInputDetail-" + recordId);
    if (!detail) return;
    if (detail.style.display === "block") { detail.style.display = "none"; btn.textContent = "输入"; return; }
    if (detail.dataset.loaded === "1") { detail.style.display = "block"; btn.textContent = "收起输入"; return; }

    detail.innerHTML = '<div class="mat-history-input-loading">加载输入信息...</div>';
    detail.style.display = "block";
    btn.textContent = "收起输入";

    fetch(API_PREFIX + "/history/" + recordId)
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.error) { detail.innerHTML = '<div class="mat-history-input-loading">加载失败</div>'; return; }
            var html = '';
            html += '<div class="mat-history-input-title">教师输入信息</div>';
            html += '<div class="mat-history-input-row"><span class="mat-history-input-label">学科：</span><span class="mat-history-input-value">' + escapeHtml(data.subject || "") + '</span></div>';
            html += '<div class="mat-history-input-row"><span class="mat-history-input-label">年级：</span><span class="mat-history-input-value">' + escapeHtml(data.grade || "") + '</span></div>';
            html += '<div class="mat-history-input-row"><span class="mat-history-input-label">语言风格：</span><span class="mat-history-input-value">' + escapeHtml(data.language_style || "未设置") + '</span></div>';
            html += '<div class="mat-history-input-row"><span class="mat-history-input-label">教学目标：</span><span class="mat-history-input-value">' + escapeHtml(data.teaching_goals || "未填写") + '</span></div>';
            html += '<div class="mat-history-input-row"><span class="mat-history-input-label">学情描述：</span><span class="mat-history-input-value">' + escapeHtml(data.student_profile || "未填写") + '</span></div>';
            html += '<div class="mat-history-input-row"><span class="mat-history-input-label">重难点分析：</span><span class="mat-history-input-value">' + escapeHtml(data.difficulty_analysis || "未填写") + '</span></div>';
            detail.innerHTML = html;
            detail.dataset.loaded = "1";
        })
        .catch(function () { detail.innerHTML = '<div class="mat-history-input-loading">加载失败</div>'; });
}

function loadHistoryItem(recordId) {
    currentTaskId = recordId;
    fetch(API_PREFIX + "/history/" + recordId)
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.error) return;
            closeHistoryDrawer();
            document.getElementById("placeholder").style.display = "none";
            document.getElementById("progressSection").style.display = "none";
            showResult(data.result, recordId);
            if (isGenerating) {
                document.getElementById("generatingBanner").style.display = "flex";
                document.getElementById("generatingBannerText").textContent = "正在生成教学地图，当前查看的是历史记录";
            }
        });
}

function loadHistoryLogs(recordId, event) {
    if (event && typeof event.stopPropagation === "function") event.stopPropagation();
    closeHistoryDrawer();
    currentTaskId = recordId;
    setUiStage("generation");
    document.getElementById("placeholder").style.display = "none";
    document.getElementById("progressSection").style.display = "none";
    document.getElementById("viewTabs").style.display = "flex";
    document.querySelectorAll(".mat-view-tab").forEach(function (b) { b.classList.remove("active"); });
    document.querySelector('.mat-view-tab[data-view="logs"]').classList.add("active");
    document.getElementById("graphSection").style.display = "none";
    document.getElementById("textSection").style.display = "none";
    document.getElementById("logsSection").style.display = "block";
    document.getElementById("detailSection").style.display = "none";
    ensureHistoryResultLoaded(recordId);
    loadAgentLogs(recordId);
}

function deleteHistoryItem(recordId, event) {
    if (event && typeof event.stopPropagation === "function") event.stopPropagation();
    if (!confirm("确定删除此记录？")) return;
    fetch(API_PREFIX + "/history/" + recordId, { method: "DELETE" })
        .then(function () { loadHistory(); });
}

function exportHistoryItem(recordId, event, btn) {
    if (event && typeof event.stopPropagation === "function") event.stopPropagation();
    if (btn) { btn.disabled = true; btn.textContent = "导出中..."; }

    fetch(API_PREFIX + "/history/" + recordId)
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.error || !data.result) {
                alert("导出失败：无法获取数据");
                return;
            }
            var md = teachingMapToMarkdown(data);
            var rawDate = String(data.created_at || recordId).replace(/[: ]/g, "-").replace(/[^\w\-]/g, "");
            var filename = (data.subject || "教学地图") + "_" + (data.grade || "") + "_" + rawDate + ".md";
            downloadTextFile(md, filename);
        })
        .catch(function (err) { alert("导出失败：" + err.message); })
        .then(function () {
            if (btn) { btn.disabled = false; btn.textContent = "导出教案"; }
        });
}

var CN_NUMBERS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十"];

function teachingMapToMarkdown(data) {
    var teachingMap = data.result || {};
    var nodes = teachingMap.nodes || [];
    var edges = teachingMap.edges || [];

    var mainNodes = nodes.filter(function (n) { return n.question_type === "main"; });
    var variantNodes = nodes.filter(function (n) { return n.question_type === "variant"; });
    var scaffoldNodes = nodes.filter(function (n) { return n.question_type === "scaffold"; });
    var mainOrder = orderMainNodes(mainNodes, edges);

    var lines = [];

    lines.push("# " + (data.subject || "") + (data.grade || "") + " 教学地图");
    lines.push("");

    lines.push("## 基本信息");
    lines.push("");
    if (data.subject) lines.push("- **学科**：" + data.subject);
    if (data.grade) lines.push("- **年级**：" + data.grade);
    if (data.teaching_goals) lines.push("- **教学目标**：" + data.teaching_goals);
    if (data.student_profile) lines.push("- **学情描述**：" + data.student_profile);
    if (data.difficulty_analysis) lines.push("- **重难点分析**：" + data.difficulty_analysis);
    if (data.language_style) lines.push("- **语言风格**：" + data.language_style);
    if (data.model_display_name || data.model_id) lines.push("- **生成模型**：" + (data.model_display_name || data.model_id || ""));
    var durationSeconds = Number(data.duration_seconds);
    if (isFinite(durationSeconds) && durationSeconds >= 0) {
        lines.push("- **生成时长**：" + formatDurationClock(durationSeconds));
    }
    if (data.created_at) lines.push("- **生成时间**：" + data.created_at);
    lines.push("");

    lines.push("## 教学地图概览");
    lines.push("");
    lines.push("共 **" + nodes.length + "** 个问题节点（主干 " + mainNodes.length + " 个、变式 " + variantNodes.length + " 个、支架 " + scaffoldNodes.length + " 个），**" + edges.length + "** 条连接关系");
    lines.push("");

    lines.push("---");
    lines.push("");

    mainOrder.forEach(function (mainNode, idx) {
        var cnNum = CN_NUMBERS[idx] || String(idx + 1);
        lines.push("## " + cnNum + "、主干问题 " + (idx + 1));
        lines.push("");
        lines.push(mainNode.content || "");
        lines.push("");

        var metaLine = buildMetaLine(mainNode);
        if (metaLine) { lines.push(metaLine); lines.push(""); }

        var commentary = getCommentary(mainNode);
        if (commentary) {
            lines.push("### 说课稿");
            lines.push("");
            lines.push(commentary);
            lines.push("");
        }

        var relatedVariants = variantNodes.filter(function (v) {
            return (v.main_id || v.parent_id) === mainNode.id;
        });
        if (relatedVariants.length > 0) {
            lines.push("### 变式问题");
            lines.push("");
            relatedVariants.forEach(function (v, vi) {
                lines.push("#### 变式 " + (vi + 1) + (v.variation_type ? "（" + v.variation_type + "）" : ""));
                lines.push("");
                lines.push(v.content || "");
                lines.push("");
                var vm = buildMetaLine(v);
                if (vm) { lines.push(vm); lines.push(""); }
                var vc = getCommentary(v);
                if (vc) { lines.push("**说课稿：**"); lines.push(""); lines.push(vc); lines.push(""); }
            });
        }

        if (idx < mainOrder.length - 1) {
            var nextMain = mainOrder[idx + 1];
            var relatedScaffolds = scaffoldNodes.filter(function (s) {
                var fromId = s.from_id || s.from_main_id;
                var toId = s.to_id || s.to_main_id;
                return fromId === mainNode.id || toId === nextMain.id;
            });
            if (relatedScaffolds.length > 0) {
                lines.push("### 支架问题（过渡到下一主干）");
                lines.push("");
                relatedScaffolds.forEach(function (s, si) {
                    lines.push("#### 支架 " + (si + 1));
                    lines.push("");
                    lines.push(s.content || "");
                    lines.push("");
                    var sm = buildMetaLine(s);
                    if (sm) { lines.push(sm); lines.push(""); }
                    var sc = getCommentary(s);
                    if (sc) { lines.push("**说课稿：**"); lines.push(""); lines.push(sc); lines.push(""); }
                    if (s.bridge_function) { lines.push("**桥梁功能：**" + s.bridge_function); lines.push(""); }
                });
            }
            lines.push("---");
            lines.push("");
        }
    });

    return lines.join("\n");
}

function buildMetaLine(node) {
    var parts = [];
    if (node.knowledge_points && node.knowledge_points.length) {
        parts.push("知识点：" + node.knowledge_points.join("、"));
    }
    var cl = node.cognitive_level || node.bloom_level || "";
    var clLabel = COGNITIVE_LABELS[cl] || cl;
    if (clLabel) parts.push("认知层次：" + clLabel);
    if (node.difficulty !== undefined) parts.push("难度：" + node.difficulty);
    var di = node.design_intent || node.design_rationale || "";
    if (di) parts.push("设计意图：" + di);
    if (!parts.length) return "";
    return parts.map(function (p) { return "- " + p; }).join("  \n");
}

function downloadTextFile(text, filename) {
    var blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Progress helpers
// ---------------------------------------------------------------------------
function addLogEntry(message, status) {
    var log = document.getElementById("progressLog");
    if (!log) return;
    var entry = document.createElement("div");
    entry.className = "mat-log-entry";
    var dot = document.createElement("span");
    dot.className = "mat-log-dot";
    if (status === "done") dot.classList.add("done");
    if (status === "error") dot.classList.add("error");
    var text = document.createElement("span");
    text.className = "mat-log-text";
    text.textContent = message;
    entry.appendChild(dot);
    entry.appendChild(text);
    log.appendChild(entry);
    log.scrollTop = log.scrollHeight;
}

function clearVisibleProgressLog() {
    var log = document.getElementById("progressLog");
    if (log) log.innerHTML = "";
}

function updateProgressBar(stepIdx) {
    var total = AGENT_STEPS.length;
    if (stepIdx < 0) return;
    var pct = Math.min(((stepIdx + 1) / total) * 95, 95);
    var bar = document.getElementById("progressBar");
    var percent = document.getElementById("matGenerationPercent");
    if (bar) bar.style.width = pct + "%";
    if (percent) percent.textContent = Math.round(pct) + "%";
}

renderGenerationDurationText();
if (!openRecordFromQueryOnLoad()) {
    restoreTaskProgressOnLoad();
}
