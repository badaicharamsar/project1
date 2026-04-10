const ALTERNATIVE_STYLES = [
  { color: "#9c6b30", dashArray: "10 8" },
  { color: "#2f7d73", dashArray: "6 8" },
  { color: "#764b7b", dashArray: "3 8" },
  { color: "#596f1c", dashArray: "12 6 2 6" },
];

function buildNodeLookup(nodes) {
  return Object.fromEntries(nodes.map((node) => [node.id, node]));
}

function pathToLatLngs(pathNodes, nodeLookup) {
  return pathNodes
    .map((nodeId) => nodeLookup[nodeId])
    .filter(Boolean)
    .map((node) => [node.latitude, node.longitude]);
}

export class ResearchMap {
  constructor(containerId) {
    this.map = L.map(containerId, {
      zoomControl: true,
      preferCanvas: true,
    }).setView([3.5952, 98.6722], 11);

    this.baseLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(this.map);

    this.edgeLayer = L.layerGroup().addTo(this.map);
    this.nodeLayer = L.layerGroup().addTo(this.map);
    this.routeLayer = L.layerGroup().addTo(this.map);
    this.alternativeLayer = L.layerGroup().addTo(this.map);

    L.control
      .layers(
        { "OpenStreetMap": this.baseLayer },
        {
          Nodes: this.nodeLayer,
          Edges: this.edgeLayer,
          "Primary Route": this.routeLayer,
          Alternatives: this.alternativeLayer,
        },
      )
      .addTo(this.map);

    this._addLegend();
  }

  resetToMedan() {
    this.map.setView([3.5952, 98.6722], 11);
  }

  _addLegend() {
    const legend = L.control({ position: "bottomleft" });
    legend.onAdd = () => {
      const div = L.DomUtil.create("div", "map-legend");
      div.innerHTML = `
        <strong>Legend</strong><br />
        <span class="legend-line"></span> Primary route<br />
        <span class="legend-line alt"></span> Alternative route<br />
        <span class="muted-note">Nodes are clickable for metadata.</span>
      `;
      return div;
    };
    legend.addTo(this.map);
  }

  renderDataset(dataset) {
    this.nodeLayer.clearLayers();
    this.edgeLayer.clearLayers();
    this.routeLayer.clearLayers();
    this.alternativeLayer.clearLayers();

    const nodeLookup = buildNodeLookup(dataset.nodes || []);
    const bounds = [];

    (dataset.edges || []).forEach((edge) => {
      const source = nodeLookup[edge.source];
      const target = nodeLookup[edge.target];
      if (!source || !target) {
        return;
      }
      const line = L.polyline(
        [
          [source.latitude, source.longitude],
          [target.latitude, target.longitude],
        ],
        {
          color: "#8da2b1",
          weight: 3,
          opacity: 0.8,
        },
      ).bindTooltip(
        `
          <strong>${edge.source} -> ${edge.target}</strong><br />
          Distance: ${edge.distance}<br />
          Time: ${edge.time}<br />
          Cost: ${edge.cost}<br />
          Road condition: ${edge.road_condition_score}
        `,
      );
      this.edgeLayer.addLayer(line);
    });

    (dataset.nodes || []).forEach((node) => {
      const marker = L.circleMarker([node.latitude, node.longitude], {
        radius: 7,
        color: node.active ? "#1d5f7a" : "#a7b4be",
        weight: 2,
        fillColor: node.active ? "#2f86aa" : "#ced7de",
        fillOpacity: 0.9,
      }).bindPopup(
        `
          <strong>${node.name}</strong><br />
          ID: ${node.id}<br />
          Latitude: ${node.latitude}<br />
          Longitude: ${node.longitude}<br />
          Metadata: <pre>${JSON.stringify(node.metadata || {}, null, 2)}</pre>
        `,
      );
      this.nodeLayer.addLayer(marker);
      bounds.push([node.latitude, node.longitude]);
    });

    if (bounds.length) {
      this.map.fitBounds(bounds, { padding: [30, 30] });
    } else {
      this.resetToMedan();
    }
  }

  renderAnalysis(dataset, primaryRoute, alternatives = [], displayMode = "graph") {
    this.routeLayer.clearLayers();
    this.alternativeLayer.clearLayers();

    if (!primaryRoute) {
      return;
    }

    const nodeLookup = buildNodeLookup(dataset.nodes || []);
    const renderMode = displayMode === "road" ? "graph" : displayMode;

    const drawRoute = (route, layer, style) => {
      const latLngs = pathToLatLngs(route.path_nodes, nodeLookup);
      if (latLngs.length < 2) {
        return;
      }
      const polyline = L.polyline(latLngs, style).bindPopup(
        `
          <strong>${route.route_id}</strong><br />
          Path: ${route.path_nodes.join(" -> ")}<br />
          Distance: ${route.total_distance}<br />
          Time: ${route.total_time}<br />
          Cost: ${route.total_cost}
        `,
      );
      layer.addLayer(polyline);
    };

    drawRoute(primaryRoute, this.routeLayer, {
      color: "#1d5f7a",
      weight: 7,
      opacity: 0.95,
      lineJoin: "round",
    });

    alternatives
      .filter((route) => route.route_id !== primaryRoute.route_id)
      .forEach((route, index) => {
        drawRoute(route, this.alternativeLayer, {
          color: ALTERNATIVE_STYLES[index % ALTERNATIVE_STYLES.length].color,
          weight: 5,
          opacity: 0.78,
          dashArray: ALTERNATIVE_STYLES[index % ALTERNATIVE_STYLES.length].dashArray,
        });
      });

    if (renderMode === "graph") {
      const focusBounds = pathToLatLngs(primaryRoute.path_nodes, nodeLookup);
      if (focusBounds.length) {
        this.map.fitBounds(focusBounds, { padding: [60, 60] });
      }
    }
  }

  exportGeoJson(dataset, primaryRoute, alternatives = []) {
    const nodeLookup = buildNodeLookup(dataset.nodes || []);
    const features = [];

    (dataset.nodes || []).forEach((node) => {
      features.push({
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [node.longitude, node.latitude],
        },
        properties: {
          kind: "node",
          id: node.id,
          name: node.name,
          active: node.active,
          ...node.metadata,
        },
      });
    });

    (dataset.edges || []).forEach((edge) => {
      const source = nodeLookup[edge.source];
      const target = nodeLookup[edge.target];
      if (!source || !target) {
        return;
      }
      features.push({
        type: "Feature",
        geometry: {
          type: "LineString",
          coordinates: [
            [source.longitude, source.latitude],
            [target.longitude, target.latitude],
          ],
        },
        properties: {
          kind: "edge",
          source: edge.source,
          target: edge.target,
          distance: edge.distance,
          time: edge.time,
          cost: edge.cost,
          road_condition_score: edge.road_condition_score,
          ...edge.metadata,
        },
      });
    });

    [primaryRoute, ...(alternatives || []).filter(Boolean)].forEach((route, index) => {
      if (!route) {
        return;
      }
      const coordinates = pathToLatLngs(route.path_nodes, nodeLookup).map(([lat, lng]) => [lng, lat]);
      if (coordinates.length < 2) {
        return;
      }
      features.push({
        type: "Feature",
        geometry: {
          type: "LineString",
          coordinates,
        },
        properties: {
          kind: index === 0 ? "primary_route" : "alternative_route",
          route_id: route.route_id,
          total_distance: route.total_distance,
          total_time: route.total_time,
          total_cost: route.total_cost,
          hops: route.hops,
        },
      });
    });

    return {
      type: "FeatureCollection",
      features,
    };
  }
}
