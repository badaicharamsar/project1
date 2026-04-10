import { api } from "./services.js";
import { ResearchMap } from "./map.js";
import { createUI } from "./ui.js";

const state = {
  dataset: { nodes: [], edges: [] },
  summary: null,
  shortestResult: null,
  hybridResult: null,
};

const ui = createUI();
const researchMap = new ResearchMap("map");

function cloneDataset(dataset) {
  return {
    nodes: (dataset.nodes || []).map((node) => ({
      ...node,
      metadata: { ...(node.metadata || {}) },
    })),
    edges: (dataset.edges || []).map((edge) => ({
      ...edge,
      metadata: { ...(edge.metadata || {}) },
    })),
  };
}

function getNodeById(nodeId) {
  return state.dataset.nodes.find((node) => node.id === nodeId);
}

function buildEdgeAlternatives(edges = []) {
  return edges.map((edge, index) => {
    const metadata = edge.metadata || {};
    return {
      alternative_id: metadata.__edge_id || `${edge.source}->${edge.target}#${index + 1}`,
      alternative_label: metadata.__edge_label || `${edge.source} -> ${edge.target}`,
      source: edge.source,
      target: edge.target,
    };
  });
}

function buildImportedCriterionOptions(edges = []) {
  const labelsByField = new Map();
  const numericFields = new Set();

  edges.forEach((edge) => {
    const metadata = edge.metadata || {};
    const columnLabels = metadata.__column_labels__ || {};

    Object.entries(columnLabels).forEach(([field, label]) => {
      if (!labelsByField.has(field)) {
        labelsByField.set(field, label);
      }
    });

    ["distance", "time", "cost", "road_condition_score"].forEach((field) => {
      if (field in columnLabels && Number.isFinite(Number(edge[field]))) {
        numericFields.add(field);
      }
    });

    Object.entries(metadata).forEach(([key, value]) => {
      if (key.startsWith("__") || key.startsWith("_")) {
        return;
      }
      if (typeof value === "number" && Number.isFinite(value)) {
        numericFields.add(key);
      }
    });
  });

  return [...numericFields]
    .sort((left, right) => {
      const leftLabel = labelsByField.get(left) || ui.prettifyFieldName(left);
      const rightLabel = labelsByField.get(right) || ui.prettifyFieldName(right);
      return leftLabel.localeCompare(rightLabel, "id");
    })
    .map((field) => ({
      id: field,
      label: labelsByField.get(field) || ui.prettifyFieldName(field),
    }));
}

function currentSelectorState() {
  return {
    shortestOrigin: ui.refs.originSelect.value,
    shortestDestination: ui.refs.destinationSelect.value,
    hybridOrigin: ui.refs.hybridOriginSelect.value,
    hybridDestination: ui.refs.hybridDestinationSelect.value,
    shortestActive: [...ui.refs.activeNodesList.querySelectorAll("input:checked")].map((item) => item.value),
    hybridActive: [...ui.refs.hybridActiveNodesList.querySelectorAll("input:checked")].map((item) => item.value),
  };
}

function buildHybridSidebarState() {
  ui.setHybridFieldOptions(buildImportedCriterionOptions(state.dataset.edges));
  ui.setHybridEdgeAlternatives(buildEdgeAlternatives(state.dataset.edges));
  ui.renderManualValuesEditor();
}

function rebuildWorkspace(preserveSelections = true) {
  const selectorState = preserveSelections ? currentSelectorState() : {};

  ui.renderNodeTable(state.dataset.nodes);
  ui.renderEdgeTable(state.dataset.edges);
  ui.renderNodeSelectors(state.dataset.nodes, selectorState);
  ui.renderEdgeNodeOptions(state.dataset.nodes, ui.refs.edgeSource.value, ui.refs.edgeTarget.value);
  ui.renderActiveNodes(state.dataset.nodes, selectorState.shortestActive || [], "shortest");
  ui.renderActiveNodes(state.dataset.nodes, selectorState.hybridActive || [], "hybrid");
  ui.renderDatasetSummary(state.dataset, state.summary);
  buildHybridSidebarState();
  researchMap.renderDataset(state.dataset);

  if (!state.dataset.nodes.length) {
    researchMap.resetToMedan();
    ui.setMapModeNote("Default view: Medan");
  }
}

function clearResults() {
  state.shortestResult = null;
  state.hybridResult = null;

  if (ui.currentView === "home") {
    ui.renderHome();
  } else if (ui.currentView === "shortest") {
    ui.renderEmptyAnalysis("shortest");
  } else {
    ui.renderEmptyAnalysis("hybrid");
  }
}

function resetWorkspace() {
  state.dataset = { nodes: [], edges: [] };
  state.summary = null;
  clearResults();
  ui.resetNodeForm();
  ui.resetEdgeForm();
  ui.renderHybridCriteria([]);
  rebuildWorkspace(false);
  researchMap.resetToMedan();
  ui.setMapModeNote("Default view: Medan");
}

function validateNode(node) {
  if (!node.id || !node.name) {
    throw new Error("Node id and name are required.");
  }
  if (!Number.isFinite(node.latitude) || !Number.isFinite(node.longitude)) {
    throw new Error("Node coordinates must be valid numbers.");
  }
}

function validateEdge(edge) {
  if (!edge.source || !edge.target) {
    throw new Error("Edge source and target are required.");
  }
  if (edge.source === edge.target) {
    throw new Error("Self-loop edges are not allowed.");
  }
  ["distance", "time", "cost", "road_condition_score"].forEach((field) => {
    if (!Number.isFinite(edge[field]) || edge[field] < 0) {
      throw new Error(`Field '${field}' must be a non-negative number.`);
    }
  });
}

function buildBasePayload(config) {
  return {
    dataset: state.dataset,
    graph_type: config.graph_type,
    metric: config.metric,
    active_node_ids: config.active_node_ids,
    custom_metric_weights: config.metric === "custom" ? config.custom_metric_weights : null,
  };
}

async function uploadWorkbook() {
  const workbookFile = ui.refs.workbookFile.files[0];
  if (!workbookFile) {
    throw new Error("Please choose one Excel workbook that contains both datafix and kordinat simpul.");
  }

  const formData = new FormData();
  formData.append("workbook_file", workbookFile);

  const response = await api.uploadWorkbook(formData);
  state.dataset = cloneDataset(response.dataset);
  state.summary = response.summary;
  clearResults();
  ui.renderHybridCriteria([]);
  rebuildWorkspace(false);

  if (response.summary?.warnings?.length) {
    ui.setFlash(response.summary.warnings[0], "warning");
    return;
  }
  ui.setFlash("Workbook imported successfully.", "success");
}

async function validateGraph() {
  const config = ui.readShortestConfig();
  const summary = await api.buildGraph(buildBasePayload(config));
  state.summary = summary;
  ui.renderDatasetSummary(state.dataset, summary);
  ui.setFlash("Graph validated successfully.", "success");
}

async function runShortestPath() {
  if (!state.dataset.nodes.length || !state.dataset.edges.length) {
    throw new Error("Import your Excel workbook first.");
  }

  const config = ui.readShortestConfig();
  if (!config.origin_id || !config.destination_id) {
    throw new Error("Please choose origin and destination.");
  }
  if (config.origin_id === config.destination_id) {
    throw new Error("Origin and destination must be different.");
  }

  const response = await api.runDijkstra({
    ...buildBasePayload(config),
    origin_id: config.origin_id,
    destination_id: config.destination_id,
  });

  state.summary = response.summary;
  state.shortestResult = response;
  ui.setMapModeNote("Shortest Path mode: Dijkstra");
  ui.renderDatasetSummary(state.dataset, state.summary);
  ui.renderShortestResults({ summary: response.summary, primaryRoute: response.result });
  researchMap.renderAnalysis(state.dataset, response.result, [response.result], "graph");
  ui.setFlash("Dijkstra shortest path completed.", "success");
}

async function runHybridAnalysis() {
  if (!state.dataset.nodes.length || !state.dataset.edges.length) {
    throw new Error("Import your workbook first in Shortest Path.");
  }

  const config = ui.readHybridConfig();
  if (!config.scenario) {
    throw new Error("Pilih skenario hybrid terlebih dahulu.");
  }
  if (!config.origin_id || !config.destination_id) {
    throw new Error("Please choose origin and destination for hybrid analysis.");
  }
  if (config.origin_id === config.destination_id) {
    throw new Error("Origin and destination must be different.");
  }
  if (!config.criteria.length) {
    throw new Error("Tambahkan minimal satu kriteria dari datafix atau input manual.");
  }

  const response = await api.runHybrid({
    dataset: state.dataset,
    origin_id: config.origin_id,
    destination_id: config.destination_id,
    graph_type: config.graph_type,
    active_node_ids: config.active_node_ids,
    scenario: config.scenario,
    method: config.method,
    weight_method: config.weight_method,
    criteria: config.criteria,
  });

  state.hybridResult = response;
  ui.setMapModeNote(
    response.scenario === "scenario_1"
      ? `Hybrid mode: ${response.method.toUpperCase()} -> Dijkstra`
      : `Hybrid mode: local ${response.method.toUpperCase()} per edge`,
  );
  ui.renderDatasetSummary(state.dataset, state.summary);
  ui.renderHybridResults(response);
  researchMap.renderAnalysis(state.dataset, response.route_result, [response.route_result], "graph");
  ui.setFlash("Hybrid analysis completed.", "success");
}

function renderCurrentView() {
  if (ui.currentView === "home") {
    ui.renderHome();
    researchMap.renderDataset(state.dataset);
    if (!state.dataset.nodes.length) {
      researchMap.resetToMedan();
    }
    ui.setResultsBadge("Ready");
    return;
  }

  if (ui.currentView === "shortest") {
    if (state.shortestResult) {
      ui.renderShortestResults({
        summary: state.shortestResult.summary,
        primaryRoute: state.shortestResult.result,
      });
      researchMap.renderAnalysis(state.dataset, state.shortestResult.result, [state.shortestResult.result], "graph");
    } else {
      ui.renderEmptyAnalysis("shortest");
      researchMap.renderDataset(state.dataset);
    }
    return;
  }

  if (state.hybridResult) {
    ui.renderHybridResults(state.hybridResult);
    researchMap.renderAnalysis(state.dataset, state.hybridResult.route_result, [state.hybridResult.route_result], "graph");
  } else {
    ui.renderEmptyAnalysis("hybrid");
    researchMap.renderDataset(state.dataset);
  }
}

function exportJson() {
  const payload = {
    dataset: state.dataset,
    summary: state.summary,
    shortest_result: state.shortestResult,
    hybrid_result: state.hybridResult,
    exported_at: new Date().toISOString(),
  };
  ui.downloadFile("research-analysis.json", JSON.stringify(payload, null, 2), "application/json");
}

function exportCsv() {
  let rows = [];

  if (ui.currentView === "hybrid" && state.hybridResult?.ranking?.length) {
    const header = ["alternative_id", "alternative_label", "score", "rank"];
    rows = [
      header.join(","),
      ...state.hybridResult.ranking.map((row) =>
        [
          row.alternative_id,
          `"${String(row.alternative_label).replaceAll('"', '""')}"`,
          row.score,
          row.rank,
        ].join(","),
      ),
    ];
  } else {
    const result = state.shortestResult?.result || state.hybridResult?.route_result;
    if (!result) {
      throw new Error("Run an analysis first before exporting CSV.");
    }

    const header = ["route_id", "path", "distance", "time", "cost", "road_condition", "hops", "optimized_weight"];
    rows = [
      header.join(","),
      [
        result.route_id,
        `"${result.path_nodes.join(" -> ")}"`,
        result.total_distance,
        result.total_time,
        result.total_cost,
        result.average_road_condition,
        result.hops,
        result.optimized_weight,
      ].join(","),
    ];
  }

  ui.downloadFile("research-analysis.csv", rows.join("\n"), "text/csv;charset=utf-8");
}

function exportGeoJson() {
  const route = ui.currentView === "hybrid" ? state.hybridResult?.route_result : state.shortestResult?.result;
  if (!route) {
    throw new Error("Run an analysis first before exporting GeoJSON.");
  }
  const geoJson = researchMap.exportGeoJson(state.dataset, route, [route]);
  ui.downloadFile("research-analysis.geojson", JSON.stringify(geoJson, null, 2), "application/geo+json");
}

function attachEvents() {
  ui.refs.navHome.addEventListener("click", () => {
    ui.setView("home");
    ui.setMapModeNote("Default view: Medan");
    renderCurrentView();
  });

  ui.refs.navShortest.addEventListener("click", () => {
    ui.setView("shortest");
    ui.setMapModeNote("Shortest Path mode: Dijkstra");
    renderCurrentView();
  });

  ui.refs.navHybrid.addEventListener("click", () => {
    ui.setView("hybrid");
    ui.setMapModeNote("Hybrid mode: pilih skenario lalu jalankan analisis");
    renderCurrentView();
  });

  ui.refs.clearWorkspaceBtn.addEventListener("click", () => {
    resetWorkspace();
    ui.setView("home");
    ui.setFlash("Workspace cleared. Map has been reset to Medan.", "warning");
  });

  ui.refs.metricSelect.addEventListener("change", ui.toggleShortestCustomMetric);
  ui.refs.hybridWeightMethodSelect.addEventListener("change", ui.toggleManualWeightArea);

  ui.refs.uploadExcelBtn.addEventListener("click", async () => {
    try {
      await uploadWorkbook();
    } catch (error) {
      ui.setFlash(error.message, "error");
    }
  });

  ui.refs.buildGraphBtn.addEventListener("click", async () => {
    try {
      await validateGraph();
    } catch (error) {
      ui.setFlash(error.message, "error");
    }
  });

  ui.refs.runShortestBtn.addEventListener("click", async () => {
    try {
      await runShortestPath();
    } catch (error) {
      ui.setFlash(error.message, "error");
    }
  });

  ui.refs.runHybridBtn.addEventListener("click", async () => {
    try {
      await runHybridAnalysis();
    } catch (error) {
      ui.setFlash(error.message, "error");
    }
  });

  ui.refs.addImportedCriterionBtn.addEventListener("click", () => {
    try {
      if (!buildImportedCriterionOptions(state.dataset.edges).length) {
        throw new Error("Belum ada kolom numerik dari sheet datafix yang bisa dipakai sebagai kriteria.");
      }
      ui.addImportedCriterion(ui.refs.hybridFieldSelect.value, ui.refs.hybridFieldKindSelect.value);
    } catch (error) {
      ui.setFlash(error.message, "error");
    }
  });

  ui.refs.addHybridCriterionBtn.addEventListener("click", () => {
    try {
      if (!state.dataset.edges.length) {
        throw new Error("Import workbook dulu agar alternatif edge dapat dibentuk.");
      }
      ui.addManualCriterion();
    } catch (error) {
      ui.setFlash(error.message, "error");
    }
  });

  ui.refs.normalizeWeightsBtn.addEventListener("click", () => {
    try {
      ui.normalizeDisplayedWeights();
      ui.setFlash("Bobot manual sudah dinormalisasi. Sigma bobot sekarang bernilai 1.", "success");
    } catch (error) {
      ui.setFlash(error.message, "error");
    }
  });

  ui.refs.hybridCriteriaEditor.addEventListener("click", (event) => {
    if (!event.target.closest(".remove-criterion-btn")) {
      return;
    }
    event.target.closest(".criterion-row")?.remove();
    ui.updateWeightTotals();
    ui.renderManualValuesEditor();
    ui.toggleManualWeightArea();
  });

  ui.refs.hybridCriteriaEditor.addEventListener("input", (event) => {
    if (event.target.classList.contains("criterion-weight")) {
      ui.updateWeightTotals();
      return;
    }
    if (event.target.classList.contains("criterion-label")) {
      ui.renderManualValuesEditor();
    }
  });

  ui.refs.nodeForm.addEventListener("submit", (event) => {
    event.preventDefault();
    try {
      const node = ui.readNodeForm();
      validateNode(node);
      const editId = ui.refs.nodeEditId.value;
      if (editId) {
        state.dataset.nodes = state.dataset.nodes.map((item) => (item.id === editId ? node : item));
      } else {
        if (getNodeById(node.id)) {
          throw new Error(`Node id '${node.id}' already exists.`);
        }
        state.dataset.nodes.push(node);
      }
      state.summary = null;
      clearResults();
      rebuildWorkspace(false);
      ui.resetNodeForm();
      ui.setFlash("Node saved in workspace.", "success");
    } catch (error) {
      ui.setFlash(error.message, "error");
    }
  });

  ui.refs.edgeForm.addEventListener("submit", (event) => {
    event.preventDefault();
    try {
      const edge = ui.readEdgeForm();
      validateEdge(edge);
      if (edge.distance > 0 && edge.metadata?._missing_distance) {
        delete edge.metadata._missing_distance;
      }
      const editIndex = ui.refs.edgeEditIndex.value;
      if (editIndex !== "") {
        state.dataset.edges[Number(editIndex)] = edge;
      } else {
        state.dataset.edges.push(edge);
      }
      state.summary = null;
      clearResults();
      rebuildWorkspace();
      ui.resetEdgeForm();
      ui.setFlash("Edge saved in workspace.", "success");
    } catch (error) {
      ui.setFlash(error.message, "error");
    }
  });

  ui.refs.clearNodeFormBtn.addEventListener("click", () => ui.resetNodeForm());
  ui.refs.clearEdgeFormBtn.addEventListener("click", () => ui.resetEdgeForm());

  ui.refs.nodesTableBody.addEventListener("click", (event) => {
    const button = event.target.closest("[data-node-action]");
    if (!button) {
      return;
    }

    const nodeId = button.dataset.nodeId;
    const node = getNodeById(nodeId);
    if (!node) {
      return;
    }

    if (button.dataset.nodeAction === "edit") {
      ui.fillNodeForm(node);
      return;
    }

    state.dataset.nodes = state.dataset.nodes.filter((item) => item.id !== nodeId);
    state.dataset.edges = state.dataset.edges.filter(
      (edge) => edge.source !== nodeId && edge.target !== nodeId,
    );
    state.summary = null;
    clearResults();
    rebuildWorkspace(false);
    ui.setFlash(`Node '${nodeId}' and its connected edges were removed.`, "warning");
  });

  ui.refs.edgesTableBody.addEventListener("click", (event) => {
    const button = event.target.closest("[data-edge-action]");
    if (!button) {
      return;
    }

    const edgeIndex = Number(button.dataset.edgeIndex);
    const edge = state.dataset.edges[edgeIndex];
    if (!edge) {
      return;
    }

    if (button.dataset.edgeAction === "edit") {
      ui.fillEdgeForm(edge, edgeIndex);
      return;
    }

    state.dataset.edges.splice(edgeIndex, 1);
    state.summary = null;
    clearResults();
    rebuildWorkspace();
    ui.setFlash("Edge removed from workspace.", "warning");
  });

  ui.refs.exportJsonBtn.addEventListener("click", () => {
    try {
      exportJson();
    } catch (error) {
      ui.setFlash(error.message, "error");
    }
  });

  ui.refs.exportCsvBtn.addEventListener("click", () => {
    try {
      exportCsv();
    } catch (error) {
      ui.setFlash(error.message, "error");
    }
  });

  ui.refs.exportGeoJsonBtn.addEventListener("click", () => {
    try {
      exportGeoJson();
    } catch (error) {
      ui.setFlash(error.message, "error");
    }
  });
}

async function bootstrap() {
  attachEvents();
  try {
    await api.health();
    resetWorkspace();
    ui.setView("home");
    ui.setFlash("Workspace siap. Silakan impor file Excel Anda untuk memulai.", "info");
  } catch (error) {
    ui.setFlash(`Failed to initialize the application: ${error.message}`, "error");
  }
}

bootstrap();
