/**
 * mat_graph.js — ECharts graph rendering for the teaching map
 */

var TYPE_COLORS = {
    main: "#4f46e5",
    variant: "#10b981",
    scaffold: "#f59e0b",
};

var TYPE_LABELS = {
    main: "主干问题",
    variant: "变式问题",
    scaffold: "支架问题",
};

var RELATION_LABELS = {
    sequence: "顺序",
    variant_of: "变式",
    scaffold_from: "支架起点",
    scaffold_sequence: "支架顺序",
    scaffold_to: "支架终点",
};

var chartInstance = null;

function wrapText(text, maxLen) {
    if (!text) return "";
    var lines = [];
    var start = 0;
    while (start < text.length) {
        lines.push(text.substring(start, start + maxLen));
        start += maxLen;
    }
    return lines.join("\n");
}

function renderGraph(teachingMap) {
    var graphSection = document.getElementById("graphSection");
    graphSection.style.display = "block";

    var container = document.getElementById("graphContainer");

    if (chartInstance) { chartInstance.dispose(); }
    chartInstance = echarts.init(container);

    var nodeCount = (teachingMap.nodes || []).length;

    var nodes = (teachingMap.nodes || []).map(function (node) {
        var qType = node.question_type || "main";
        var isMain = qType === "main";
        var symbolSize = isMain ? 52 : 38;
        var content = node.content || "";

        return {
            id: node.id,
            name: node.id,
            symbolSize: symbolSize,
            category: isMain ? 0 : qType === "variant" ? 1 : 2,
            itemStyle: {
                color: TYPE_COLORS[qType] || "#94a3b8",
                borderColor: "#fff",
                borderWidth: 2,
                shadowBlur: 6,
                shadowColor: "rgba(0,0,0,0.12)",
            },
            label: {
                show: true,
                position: "inside",
                formatter: node.id,
                fontSize: isMain ? 13 : 11,
                fontWeight: isMain ? "bold" : "normal",
                color: "#fff",
            },
            tooltip: {
                formatter: function () {
                    var typeLabel = TYPE_LABELS[qType] || qType;
                    var cognitiveLevel = node.cognitive_level || node.bloom_level || "";
                    var commentary = node.lesson_presentation_script || node.commentary || node.Commentary || "";
                    var fromId = node.from_id || node.from_main_id || "";
                    var toId = node.to_id || node.to_main_id || "";
                    var html = '<div style="max-width:420px;white-space:normal;word-break:break-word;line-height:1.6">';
                    html += '<strong style="font-size:14px">' + node.id + '</strong>';
                    html += ' <span style="color:' + TYPE_COLORS[qType] + '">[' + typeLabel + ']</span><br/>';
                    html += '<div style="margin-top:6px;font-size:13px">' + (content || "") + '</div>';
                    if (cognitiveLevel) html += '<div style="margin-top:6px;color:#888;font-size:12px">认知层次: ' + cognitiveLevel + '</div>';
                    if (node.difficulty !== undefined) html += '<div style="color:#888;font-size:12px">难度: ' + node.difficulty + '</div>';
                    if (node.knowledge_points && node.knowledge_points.length) html += '<div style="color:#888;font-size:12px">知识点: ' + node.knowledge_points.join("、") + '</div>';
                    if (qType === "scaffold" && fromId && toId) html += '<div style="color:#888;font-size:12px">桥接: ' + fromId + ' → ' + toId + '</div>';
                    if (commentary) html += '<div style="margin-top:8px;padding-top:6px;border-top:1px dashed #d1d5db;color:#334155;font-size:12px">说课稿: ' + commentary + '</div>';
                    html += '</div>';
                    return html;
                },
            },
            _raw: node,
        };
    });

    var edges = (teachingMap.edges || []).map(function (edge) {
        var lineStyle = { width: 2, curveness: 0.15 };
        var relation = edge.relation || "";

        if (relation === "sequence") { lineStyle.color = "#4f46e5"; lineStyle.width = 3; lineStyle.type = "solid"; lineStyle.curveness = 0.1; }
        else if (relation === "variant_of") { lineStyle.color = "#10b981"; lineStyle.type = "dashed"; lineStyle.curveness = 0.2; }
        else if (relation === "scaffold_from" || relation === "scaffold_to") { lineStyle.color = "#f59e0b"; lineStyle.type = "dotted"; lineStyle.width = 2; lineStyle.curveness = 0.2; }
        else if (relation === "scaffold_sequence") { lineStyle.color = "#f59e0b"; lineStyle.type = "solid"; lineStyle.width = 2; lineStyle.curveness = 0.1; }
        else { lineStyle.color = "#94a3b8"; lineStyle.type = "dotted"; }

        return { source: edge.source, target: edge.target, lineStyle: lineStyle, _raw: edge };
    });

    var categories = [{ name: "主干问题" }, { name: "变式问题" }, { name: "支架问题" }];
    var repulsion = Math.max(400, nodeCount * 35);

    var option = {
        tooltip: {
            trigger: "item",
            confine: true,
            enterable: true,
            extraCssText: "max-width:440px;white-space:normal;",
            formatter: function (params) {
                if (params.dataType === "edge") {
                    var raw = params.data._raw;
                    var relationLabel = RELATION_LABELS[raw.relation] || raw.relation;
                    return raw.source + " → " + raw.target + "<br/>关系: " + relationLabel + "<br/>权重: " + raw.weight;
                }
                return null;
            },
        },
        animationDuration: 800,
        animationEasingUpdate: "quinticInOut",
        series: [{
            type: "graph",
            layout: "force",
            data: nodes,
            links: edges,
            categories: categories,
            roam: true,
            draggable: true,
            force: { repulsion: repulsion, edgeLength: [120, 280], gravity: 0.05, layoutAnimation: true },
            emphasis: { focus: "adjacency", lineStyle: { width: 4 } },
            edgeSymbol: ["none", "arrow"],
            edgeSymbolSize: [4, 10],
        }],
    };

    chartInstance.setOption(option);

    chartInstance.on("click", function (params) {
        if (params.dataType === "node") showNodeDetail(params.data._raw);
    });

    window.addEventListener("resize", function () { if (chartInstance) chartInstance.resize(); });
}

function showNodeDetail(node) {
    var section = document.getElementById("detailSection");
    var title = document.getElementById("detailTitle");
    var content = document.getElementById("detailContent");

    section.style.display = "block";

    var qType = node.question_type || "main";
    var typeLabel = TYPE_LABELS[qType] || qType;
    var tagClass = "mat-tag mat-tag-" + qType;

    title.innerHTML = node.id + ' <span class="' + tagClass + '">' + typeLabel + '</span>';

    var html = "";
    var cognitiveLevel = node.cognitive_level || node.bloom_level || "-";
    var designIntent = node.design_intent || node.design_rationale || "";
    var commentary = node.lesson_presentation_script || node.commentary || node.Commentary || "";
    var mainId = node.main_id || node.parent_id || "";
    var fromId = node.from_id || node.from_main_id || "";
    var toId = node.to_id || node.to_main_id || "";
    html += row("问题内容", node.content || "-");
    html += row("知识点", (node.knowledge_points || []).join("、") || "-");
    html += row("认知层次", cognitiveLevel);
    html += row("难度", node.difficulty !== undefined ? node.difficulty : "-");
    if (mainId) html += row("关联主干", mainId);
    if (fromId && toId) html += row("桥接位置", fromId + " → " + toId);
    if (designIntent) html += row("设计意图", designIntent);
    if (node.variation_type) html += row("变式方式", node.variation_type);
    if (node.bridge_function) html += row("桥梁功能", node.bridge_function);
    if (commentary) html += row("说课稿", commentary);

    content.innerHTML = html;
    section.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function row(label, value) {
    return '<div class="mat-detail-content-row"><span class="mat-detail-label">' + label + '</span><span class="mat-detail-value">' + value + '</span></div>';
}
