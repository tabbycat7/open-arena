/**
 * mat_graph.js — ECharts graph rendering for the teaching map
 */

var TYPE_COLORS = {
    main: "#3a9bff",
    variant: "#4fc06a",
    scaffold: "#ffb33c",
};

// 像素描边色与字体（与 pixel-theme.css 一致）
var PX_INK = "#34384f";
var PX_FONT = '"Press Start 2P", "Zpix", monospace';

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
var graphMarkdownOptionsApplied = false;

function escapeGraphHtml(text) {
    var div = document.createElement("div");
    div.innerText = text == null ? "" : String(text);
    return div.innerHTML;
}

function renderGraphMarkdownHtml(text) {
    var source = text == null ? "" : String(text);
    if (!source) return "";

    if (typeof marked !== "undefined" && marked && typeof marked.parse === "function") {
        if (!graphMarkdownOptionsApplied && typeof marked.setOptions === "function") {
            marked.setOptions({ gfm: true, breaks: true });
            graphMarkdownOptionsApplied = true;
        }
        var rendered = marked.parse(source);
        if (typeof DOMPurify !== "undefined" && DOMPurify && typeof DOMPurify.sanitize === "function") {
            return DOMPurify.sanitize(rendered, { USE_PROFILES: { html: true } });
        }
        return escapeGraphHtml(source).replace(/\n/g, "<br>");
    }

    return escapeGraphHtml(source).replace(/\n/g, "<br>");
}

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
            symbol: "rect",
            symbolSize: symbolSize,
            category: isMain ? 0 : qType === "variant" ? 1 : 2,
            itemStyle: {
                color: TYPE_COLORS[qType] || "#94a3b8",
                borderColor: PX_INK,
                borderWidth: 3,
                shadowBlur: 0,
                shadowColor: PX_INK,
                shadowOffsetX: 4,
                shadowOffsetY: 4,
            },
            label: {
                show: true,
                position: "inside",
                formatter: node.id,
                fontSize: isMain ? 12 : 10,
                fontFamily: PX_FONT,
                fontWeight: isMain ? "bold" : "normal",
                color: "#fff",
                textShadowColor: PX_INK,
                textShadowBlur: 0,
                textShadowOffsetX: 1,
                textShadowOffsetY: 1,
            },
            tooltip: {
                formatter: function () {
                    var typeLabel = TYPE_LABELS[qType] || qType;
                    var cognitiveLevel = node.cognitive_level || node.bloom_level || "";
                    var commentary = node.lesson_presentation_script || node.commentary || node.Commentary || "";
                    var fromId = node.from_id || node.from_main_id || "";
                    var toId = node.to_id || node.to_main_id || "";
                    var html = '<div style="max-width:420px;white-space:normal;word-break:break-word;line-height:1.6">';
                    html += '<strong style="font-size:14px">' + escapeGraphHtml(node.id) + '</strong>';
                    html += ' <span style="color:' + TYPE_COLORS[qType] + '">[' + escapeGraphHtml(typeLabel) + ']</span><br/>';
                    html += '<div style="margin-top:6px;font-size:13px">' + renderGraphMarkdownHtml(content || "") + '</div>';
                    if (cognitiveLevel) html += '<div style="margin-top:6px;color:#888;font-size:12px">认知层次: ' + escapeGraphHtml(cognitiveLevel) + '</div>';
                    if (node.difficulty !== undefined) html += '<div style="color:#888;font-size:12px">难度: ' + escapeGraphHtml(node.difficulty) + '</div>';
                    if (node.knowledge_points && node.knowledge_points.length) html += '<div style="color:#888;font-size:12px">知识点: ' + escapeGraphHtml(node.knowledge_points.join("、")) + '</div>';
                    if (qType === "scaffold" && fromId && toId) html += '<div style="color:#888;font-size:12px">桥接: ' + escapeGraphHtml(fromId) + ' → ' + escapeGraphHtml(toId) + '</div>';
                    if (commentary) html += '<div style="margin-top:8px;padding-top:6px;border-top:1px dashed #d1d5db;color:#334155;font-size:12px"><div style="font-weight:600;margin-bottom:4px">说课稿</div>' + renderGraphMarkdownHtml(commentary) + '</div>';
                    html += '</div>';
                    return html;
                },
            },
            _raw: node,
        };
    });

    var edges = (teachingMap.edges || []).map(function (edge) {
        // 像素直线：去掉曲率，硬朗连线
        var lineStyle = { width: 3, curveness: 0, cap: "butt" };
        var relation = edge.relation || "";

        if (relation === "sequence") { lineStyle.color = "#3a9bff"; lineStyle.width = 4; lineStyle.type = "solid"; }
        else if (relation === "variant_of") { lineStyle.color = "#4fc06a"; lineStyle.type = "dashed"; }
        else if (relation === "scaffold_from" || relation === "scaffold_to") { lineStyle.color = "#ffb33c"; lineStyle.type = "dotted"; lineStyle.width = 3; }
        else if (relation === "scaffold_sequence") { lineStyle.color = "#ffb33c"; lineStyle.type = "solid"; lineStyle.width = 3; }
        else { lineStyle.color = "#8a90ad"; lineStyle.type = "dotted"; }

        return { source: edge.source, target: edge.target, lineStyle: lineStyle, _raw: edge };
    });

    var categories = [{ name: "主干问题" }, { name: "变式问题" }, { name: "支架问题" }];
    var repulsion = Math.max(400, nodeCount * 35);

    var option = {
        backgroundColor: "transparent",
        textStyle: { fontFamily: PX_FONT },
        tooltip: {
            trigger: "item",
            confine: true,
            enterable: true,
            backgroundColor: "#ffffff",
            borderColor: PX_INK,
            borderWidth: 3,
            padding: 12,
            textStyle: { color: PX_INK, fontFamily: '"Zpix", monospace' },
            extraCssText: "max-width:440px;white-space:normal;border-radius:0;box-shadow:4px 4px 0 " + PX_INK + ";",
            formatter: function (params) {
                if (params.dataType === "edge") {
                    var raw = params.data._raw;
                    var relationLabel = RELATION_LABELS[raw.relation] || raw.relation;
                    return escapeGraphHtml(raw.source) + " → " + escapeGraphHtml(raw.target) + "<br/>关系: " + escapeGraphHtml(relationLabel) + "<br/>权重: " + escapeGraphHtml(raw.weight);
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
    var safeQType = qType === "main" || qType === "variant" || qType === "scaffold" ? qType : "main";
    var tagClass = "mat-tag mat-tag-" + safeQType;

    title.innerHTML = escapeGraphHtml(node.id) + ' <span class="' + tagClass + '">' + escapeGraphHtml(typeLabel) + '</span>';

    var html = "";
    var cognitiveLevel = node.cognitive_level || node.bloom_level || "-";
    var designIntent = node.design_intent || node.design_rationale || "";
    var commentary = node.lesson_presentation_script || node.commentary || node.Commentary || "";
    var mainId = node.main_id || node.parent_id || "";
    var fromId = node.from_id || node.from_main_id || "";
    var toId = node.to_id || node.to_main_id || "";
    html += row("问题内容", node.content || "-", { markdown: true });
    html += row("知识点", (node.knowledge_points || []).join("、") || "-");
    html += row("认知层次", cognitiveLevel);
    html += row("难度", node.difficulty !== undefined ? node.difficulty : "-");
    if (mainId) html += row("关联主干", mainId);
    if (fromId && toId) html += row("桥接位置", fromId + " → " + toId);
    if (designIntent) html += row("设计意图", designIntent, { markdown: true });
    if (node.variation_type) html += row("变式方式", node.variation_type);
    if (node.bridge_function) html += row("桥梁功能", node.bridge_function, { markdown: true });
    if (commentary) html += row("说课稿", commentary, { markdown: true });

    content.innerHTML = html;
    section.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function row(label, value, options) {
    var useMarkdown = options && options.markdown;
    var valueHtml = useMarkdown
        ? renderGraphMarkdownHtml(value)
        : escapeGraphHtml(value);
    var valueClass = useMarkdown ? "mat-detail-value mat-markdown-content" : "mat-detail-value";
    return '<div class="mat-detail-content-row"><span class="mat-detail-label">' + escapeGraphHtml(label) + '</span><div class="' + valueClass + '">' + valueHtml + '</div></div>';
}
