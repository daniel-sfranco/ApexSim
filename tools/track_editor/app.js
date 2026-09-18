/**
 * ApexSim — Track Annotation Tool (Contrato D3 -> Contrato D4)
 * Trilha: Modelagem de Pista, Estratégia & IA (Daniel Franco)
 */

(function () {
  'use strict';

  // --- Estado da Aplicação ---
  const state = {
    circuitId: 'interlagos',
    circuitData: null, // { circuit_id, length_m, points, meta }
    zones: [], // Array de { id, type, start_m, end_m, props }
    
    // Modo de Interação: 'edit' (anotação de intervalo) ou 'view' (inspeção de zonas)
    interactionMode: 'edit',

    // Seleção de Intervalo
    selection: {
      start_m: 0,
      end_m: 500,
      isSinglePoint: false,
      activePointTarget: 'start', // 'start' ou 'end'
    },
    
    // Edição
    editingZoneId: null,
    
    // Cursor e Interação
    hover: {
      distance_m: 0,
      pointIndex: 0,
      x: 0,
      y: 0,
      isOnTrack: false,
      activeZones: [],
    },
    
    // Viewport 2D (Pan & Zoom)
    viewport: {
      zoom: 1,
      panX: 0,
      panY: 0,
      isDragging: false,
      dragStartX: 0,
      dragStartY: 0,
    },
    
    // Opções de visualização
    viewOptions: {
      showPoints: false,
      showLabels: true,
      selectedZoneId: null,
    },
    
    // Filtro ativo da lista e mapa
    activeFilter: 'all',
  };

  // Cores semânticas para as zonas
  const ZONE_COLORS = {
    sector_1: '#388bfd',
    sector_2: '#a371f7',
    sector_3: '#f0883e',
    drs_activation: '#2ea043',
    drs_detection: '#3fb950',
    braking_zone: '#f85149',
    pit_lane: '#db6d28',
    pit_entry: '#e3b341',
    pit_exit: '#d29922',
    corner: '#e3b341',
    straight: '#56d364',
    overtaking_spot: '#f778ba',
    default: '#8b949e',
  };

  // Elementos do DOM
  const dom = {
    circuitSelect: document.getElementById('circuitSelect'),
    btnLoadD3: document.getElementById('btnLoadD3'),
    d3FileInput: document.getElementById('d3FileInput'),
    btnImportD4: document.getElementById('btnImportD4'),
    d4FileInput: document.getElementById('d4FileInput'),
    btnSaveToDisk: document.getElementById('btnSaveToDisk'),
    btnExportD4: document.getElementById('btnExportD4'),
    validationStatusBadge: document.getElementById('validationStatusBadge'),
    validationIcon: document.getElementById('validationIcon'),
    validationText: document.getElementById('validationText'),
    
    // Modos
    btnModeEdit: document.getElementById('btnModeEdit'),
    btnModeView: document.getElementById('btnModeView'),

    // Viewport
    canvasContainer: document.getElementById('canvasContainer'),
    trackCanvas: document.getElementById('trackCanvas'),
    btnZoomIn: document.getElementById('btnZoomIn'),
    btnZoomOut: document.getElementById('btnZoomOut'),
    btnResetView: document.getElementById('btnResetView'),
    btnTogglePoints: document.getElementById('btnTogglePoints'),
    btnToggleLabels: document.getElementById('btnToggleLabels'),
    
    // HUD
    hudOverlay: document.getElementById('hudOverlay'),
    hudDistance: document.getElementById('hudDistance'),
    hudPointIndex: document.getElementById('hudPointIndex'),
    hudCoords: document.getElementById('hudCoords'),
    hudActiveZones: document.getElementById('hudActiveZones'),
    
    // Timeline
    timelineCanvas: document.getElementById('timelineCanvas'),
    timelineLengthMeta: document.getElementById('timelineLengthMeta'),
    
    // Form
    formModeTitle: document.getElementById('formModeTitle'),
    pointModeBadge: document.getElementById('pointModeBadge'),
    inputStartM: document.getElementById('inputStartM'),
    inputEndM: document.getElementById('inputEndM'),
    selectionDeltaText: document.getElementById('selectionDeltaText'),
    checkSinglePoint: document.getElementById('checkSinglePoint'),
    btnStartMinus10: document.getElementById('btnStartMinus10'),
    btnStartPlus10: document.getElementById('btnStartPlus10'),
    btnEndMinus10: document.getElementById('btnEndMinus10'),
    btnEndPlus10: document.getElementById('btnEndPlus10'),
    selectZoneType: document.getElementById('selectZoneType'),
    dynamicPropsContainer: document.getElementById('dynamicPropsContainer'),
    btnSaveZone: document.getElementById('btnSaveZone'),
    btnCancelEdit: document.getElementById('btnCancelEdit'),
    
    // List & Filters
    zonesCount: document.getElementById('zonesCount'),
    btnClearAllZones: document.getElementById('btnClearAllZones'),
    zonesListContainer: document.getElementById('zonesListContainer'),
    filterChips: document.querySelectorAll('.filter-chip'),
    
    // Modal
    validationModal: document.getElementById('validationModal'),
    validationModalBody: document.getElementById('validationModalBody'),
    btnCloseValidationModal: document.getElementById('btnCloseValidationModal'),
    btnOkValidationModal: document.getElementById('btnOkValidationModal'),
  };

  // Contextos gráficos dos Canvas
  const ctx = dom.trackCanvas.getContext('2d');
  const timelineCtx = dom.timelineCanvas.getContext('2d');

  // --- Inicialização ---
  function init() {
    setupEventListeners();
    handleResize();
    loadCircuit(state.circuitId);
  }

  // Helper para filtrar zonas ativas conforme filtro selecionado
  function getVisibleZones() {
    if (state.activeFilter === 'all') return state.zones;
    if (state.activeFilter === 'drs') return state.zones.filter(z => z.type.startsWith('drs_'));
    if (state.activeFilter === 'pit') return state.zones.filter(z => z.type.startsWith('pit_'));
    return state.zones.filter(z => z.type === state.activeFilter);
  }

  // --- Carregamento de Dados ---
  function loadCircuit(circuitId) {
    state.circuitId = circuitId;
    state.zones = [];
    state.editingZoneId = null;

    // 1. Tentar buscar mapa anotado existente na API (/api/track-maps/{circuitId})
    fetch(`/api/track-maps/${circuitId}`)
      .then(res => {
        if (res.ok) return res.json();
        throw new Error('Track map ainda não existe em track_maps/');
      })
      .then(data => {
        console.log(`Carregado mapa semântico existente de track_maps/${circuitId}.json`);
        state.circuitData = data;
        state.zones = (data.zones || []).map((z, idx) => ({
          id: 'zone_' + Date.now() + '_' + idx,
          type: z.type,
          start_m: z.start_m,
          end_m: z.end_m,
          props: z.props || {}
        }));
        onCircuitLoaded();
      })
      .catch(() => {
        // 2. Fallback: carregar D3 básico do bundle ou fetch
        if (window.APEX_CIRCUITS && window.APEX_CIRCUITS[circuitId]) {
          state.circuitData = JSON.parse(JSON.stringify(window.APEX_CIRCUITS[circuitId]));
          onCircuitLoaded();
        } else {
          fetch(`/circuits/${circuitId}.json`)
            .then(res => res.json())
            .then(data => {
              state.circuitData = data;
              onCircuitLoaded();
            })
            .catch(err => {
              console.warn('Circuito não encontrado:', err);
            });
        }
      });
  }

  function onCircuitLoaded() {
    if (!state.circuitData || !state.circuitData.points) return;
    
    const maxL = state.circuitData.length_m || 4000;
    dom.inputStartM.max = maxL;
    dom.inputEndM.max = maxL;

    state.selection.start_m = 0;
    state.selection.end_m = Math.min(500, maxL);
    updateSelectionUI();

    resetViewport();
    renderDynamicPropsForm();
    renderZonesList();
    validateD4Schema();
    drawAll();
  }

  // --- Transformação de Coordenadas 2D ---
  function getTrackBounds() {
    if (!state.circuitData || !state.circuitData.points.length) {
      return { minX: -500, maxX: 500, minY: -500, maxY: 500, width: 1000, height: 1000, centerX: 0, centerY: 0 };
    }
    const pts = state.circuitData.points;
    let minX = pts[0].x, maxX = pts[0].x, minY = pts[0].y, maxY = pts[0].y;
    for (let i = 1; i < pts.length; i++) {
      if (pts[i].x < minX) minX = pts[i].x;
      if (pts[i].x > maxX) maxX = pts[i].x;
      if (pts[i].y < minY) minY = pts[i].y;
      if (pts[i].y > maxY) maxY = pts[i].y;
    }
    return {
      minX, maxX, minY, maxY,
      width: maxX - minX,
      height: maxY - minY,
      centerX: (minX + maxX) / 2,
      centerY: (minY + maxY) / 2
    };
  }

  function resetViewport() {
    state.viewport.zoom = 1;
    state.viewport.panX = 0;
    state.viewport.panY = 0;
  }

  function worldToCanvas(wx, wy) {
    const bounds = getTrackBounds();
    const w = dom.trackCanvas.width;
    const h = dom.trackCanvas.height;
    const padding = 80;
    const scaleX = (w - padding * 2) / (bounds.width || 1);
    const scaleY = (h - padding * 2) / (bounds.height || 1);
    const baseScale = Math.min(scaleX, scaleY);
    const scale = baseScale * state.viewport.zoom;

    // Y invertido para coincidir com convenção cartesiana (FastF1/Matplotlib)
    const cx = w / 2 + state.viewport.panX + (wx - bounds.centerX) * scale;
    const cy = h / 2 + state.viewport.panY - (wy - bounds.centerY) * scale;
    return { x: cx, y: cy, scale };
  }

  function canvasToWorld(cx, cy) {
    const bounds = getTrackBounds();
    const w = dom.trackCanvas.width;
    const h = dom.trackCanvas.height;
    const padding = 80;
    const scaleX = (w - padding * 2) / (bounds.width || 1);
    const scaleY = (h - padding * 2) / (bounds.height || 1);
    const baseScale = Math.min(scaleX, scaleY);
    const scale = baseScale * state.viewport.zoom;

    const wx = bounds.centerX + (cx - (w / 2 + state.viewport.panX)) / scale;
    const wy = bounds.centerY - (cy - (h / 2 + state.viewport.panY)) / scale;
    return { x: wx, y: wy };
  }

  // --- Projeção de Ponto na Polyline ---
  function findClosestTrackPoint(wx, wy) {
    if (!state.circuitData || !state.circuitData.points || state.circuitData.points.length < 2) {
      return null;
    }
    const pts = state.circuitData.points;
    const len = pts.length;
    let bestDistSq = Infinity;
    let bestT = 0;
    let bestSegIndex = 0;
    let bestPoint = { x: pts[0].x, y: pts[0].y };

    for (let i = 0; i < len; i++) {
      const pA = pts[i];
      const pB = pts[(i + 1) % len];
      
      const dx = pB.x - pA.x;
      const dy = pB.y - pA.y;
      const segLenSq = dx * dx + dy * dy;

      let t = 0;
      if (segLenSq > 1e-6) {
        t = ((wx - pA.x) * dx + (wy - pA.y) * dy) / segLenSq;
        t = Math.max(0, Math.min(1, t));
      }

      const projX = pA.x + t * dx;
      const projY = pA.y + t * dy;
      const distSq = (wx - projX) * (wx - projX) + (wy - projY) * (wy - projY);

      if (distSq < bestDistSq) {
        bestDistSq = distSq;
        bestT = t;
        bestSegIndex = i;
        bestPoint = { x: projX, y: projY };
      }
    }

    const pA = pts[bestSegIndex];
    const isClosingSegment = bestSegIndex === len - 1;
    let distA = pA.distance_m;
    let distB = isClosingSegment ? state.circuitData.length_m : pts[(bestSegIndex + 1) % len].distance_m;
    
    let interpolatedDist = distA + bestT * (distB - distA);
    interpolatedDist = Math.max(0, Math.min(state.circuitData.length_m, interpolatedDist));

    return {
      distance_m: Math.round(interpolatedDist * 10) / 10,
      pointIndex: bestSegIndex,
      x: Math.round(bestPoint.x * 100) / 100,
      y: Math.round(bestPoint.y * 100) / 100,
      pixelDist: Math.sqrt(bestDistSq),
    };
  }

  // --- Desenho 2D do Canvas ---
  function drawTrack() {
    const w = dom.trackCanvas.width;
    const h = dom.trackCanvas.height;
    ctx.clearRect(0, 0, w, h);

    if (!state.circuitData || !state.circuitData.points || !state.circuitData.points.length) {
      ctx.fillStyle = '#6e7681';
      ctx.font = '14px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Nenhum circuito carregado.', w / 2, h / 2);
      return;
    }

    const pts = state.circuitData.points;
    const len = pts.length;

    // 1. Linha do Traçado Base (Asfalto / Polyline D3)
    ctx.beginPath();
    const firstP = worldToCanvas(pts[0].x, pts[0].y);
    ctx.moveTo(firstP.x, firstP.y);
    for (let i = 1; i < len; i++) {
      const cp = worldToCanvas(pts[i].x, pts[i].y);
      ctx.lineTo(cp.x, cp.y);
    }
    ctx.lineTo(firstP.x, firstP.y);

    ctx.strokeStyle = '#2d333b';
    ctx.lineWidth = 14 * state.viewport.zoom;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.stroke();

    ctx.strokeStyle = '#444c56';
    ctx.lineWidth = 8 * state.viewport.zoom;
    ctx.stroke();

    // 2. Renderizar Zonas Cadastradas sobre o Traçado (Filtradas)
    renderTrackZones();

    // 3. Renderizar Destaque do Intervalo Selecionado (Apenas se em modo Anotação)
    if (state.interactionMode === 'edit') {
      renderSelectedIntervalTrack();
    }

    // 4. Pontos Geométricos D3 (opcional)
    if (state.viewOptions.showPoints) {
      ctx.fillStyle = 'rgba(88, 166, 255, 0.7)';
      for (let i = 0; i < len; i++) {
        const cp = worldToCanvas(pts[i].x, pts[i].y);
        ctx.beginPath();
        ctx.arc(cp.x, cp.y, 3 * Math.sqrt(state.viewport.zoom), 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // 5. Linha de Largada e Chegada (0m)
    const startP = worldToCanvas(pts[0].x, pts[0].y);
    const pNext = worldToCanvas(pts[1].x, pts[1].y);
    const angle = Math.atan2(pNext.y - startP.y, pNext.x - startP.x) + Math.PI / 2;
    const markLen = 16 * state.viewport.zoom;

    ctx.save();
    ctx.translate(startP.x, startP.y);
    ctx.rotate(angle);
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(-markLen, 0);
    ctx.lineTo(markLen, 0);
    ctx.stroke();
    
    ctx.rotate(-Math.PI / 2);
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 11px sans-serif';
    ctx.fillText('🏁 LARGADA (0m)', 12, 4);
    ctx.restore();

    // 6. Rótulos das Curvas / Marcadores (Filtrados)
    if (state.viewOptions.showLabels) {
      renderTrackLabels();
    }

    // 7. Cursor e Snap Magnético
    if (state.hover.isOnTrack) {
      const snapP = worldToCanvas(state.hover.x, state.hover.y);
      ctx.beginPath();
      ctx.arc(snapP.x, snapP.y, 6, 0, Math.PI * 2);
      ctx.fillStyle = state.interactionMode === 'view' ? '#a371f7' : '#39c5bb';
      ctx.fill();
      ctx.lineWidth = 2;
      ctx.strokeStyle = '#ffffff';
      ctx.stroke();

      ctx.strokeStyle = state.interactionMode === 'view' ? 'rgba(163, 113, 247, 0.5)' : 'rgba(57, 197, 187, 0.5)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(snapP.x - 14, snapP.y);
      ctx.lineTo(snapP.x + 14, snapP.y);
      ctx.moveTo(snapP.x, snapP.y - 14);
      ctx.lineTo(snapP.x, snapP.y + 14);
      ctx.stroke();
    }
  }

  function renderTrackZones() {
    const visibleZones = getVisibleZones();
    if (!visibleZones.length) return;

    visibleZones.forEach(zone => {
      const isSelected = state.viewOptions.selectedZoneId === zone.id;
      let color = ZONE_COLORS[zone.type] || ZONE_COLORS.default;
      if (zone.type === 'sector') {
        color = ZONE_COLORS[`sector_${zone.props?.number || 1}`] || ZONE_COLORS.sector_1;
      }

      if (zone.start_m === zone.end_m) {
        // Zona pontual
        const pt = getCoordAtDistance(zone.start_m);
        if (pt) {
          const cp = worldToCanvas(pt.x, pt.y);
          ctx.beginPath();
          ctx.arc(cp.x, cp.y, isSelected ? 9 : 5, 0, Math.PI * 2);
          ctx.fillStyle = color;
          ctx.fill();
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = isSelected ? 3 : 1.5;
          ctx.stroke();
        }
      } else {
        // Zona de intervalo
        drawTrackSegment(zone.start_m, zone.end_m, color, isSelected ? 13 : 7, isSelected ? 0.95 : 0.65);
      }
    });
  }

  function renderSelectedIntervalTrack() {
    const s = state.selection;
    if (s.isSinglePoint) {
      const pt = getCoordAtDistance(s.start_m);
      if (pt) {
        const cp = worldToCanvas(pt.x, pt.y);
        ctx.beginPath();
        ctx.arc(cp.x, cp.y, 9, 0, Math.PI * 2);
        ctx.fillStyle = '#e3b341';
        ctx.fill();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 3;
        ctx.stroke();

        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 11px monospace';
        ctx.fillText(`P (${s.start_m}m)`, cp.x + 12, cp.y + 4);
      }
    } else if (s.start_m <= s.end_m) {
      drawTrackSegment(s.start_m, s.end_m, '#e3b341', 11, 0.9);

      const ptA = getCoordAtDistance(s.start_m);
      const ptB = getCoordAtDistance(s.end_m);

      if (ptA) {
        const cpA = worldToCanvas(ptA.x, ptA.y);
        drawFlagMarker(cpA.x, cpA.y, 'A', '#388bfd', `${s.start_m}m`);
      }
      if (ptB) {
        const cpB = worldToCanvas(ptB.x, ptB.y);
        drawFlagMarker(cpB.x, cpB.y, 'B', '#f85149', `${s.end_m}m`);
      }
    }
  }

  function drawFlagMarker(cx, cy, letter, bgColor, distText) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, 10, 0, Math.PI * 2);
    ctx.fillStyle = bgColor;
    ctx.fill();
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 2;
    ctx.stroke();

    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 10px monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(letter, cx, cy);

    ctx.font = 'bold 10px monospace';
    ctx.fillStyle = '#f0f6fc';
    ctx.fillText(distText, cx, cy - 16);
    ctx.restore();
  }

  function drawTrackSegment(startM, endM, color, strokeWidth, alpha = 0.7) {
    if (!state.circuitData || !state.circuitData.points.length) return;
    const pts = state.circuitData.points;
    const len = pts.length;
    const totalL = state.circuitData.length_m;

    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = color;
    ctx.lineWidth = strokeWidth * state.viewport.zoom;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();

    let started = false;

    for (let i = 0; i < len; i++) {
      const pA = pts[i];
      const isLast = i === len - 1;
      const pB = pts[(i + 1) % len];
      const distA = pA.distance_m;
      const distB = isLast ? totalL : pB.distance_m;

      if (distB >= startM && distA <= endM) {
        const t0 = Math.max(0, Math.min(1, (startM - distA) / (distB - distA || 1)));
        const t1 = Math.max(0, Math.min(1, (endM - distA) / (distB - distA || 1)));

        const x0 = pA.x + t0 * (pB.x - pA.x);
        const y0 = pA.y + t0 * (pB.y - pA.y);
        const x1 = pA.x + t1 * (pB.x - pA.x);
        const y1 = pA.y + t1 * (pB.y - pA.y);

        const c0 = worldToCanvas(x0, y0);
        const c1 = worldToCanvas(x1, y1);

        if (!started) {
          ctx.moveTo(c0.x, c0.y);
          started = true;
        } else {
          ctx.lineTo(c0.x, c0.y);
        }
        ctx.lineTo(c1.x, c1.y);
      }
    }

    ctx.stroke();
    ctx.restore();
  }

  function renderTrackLabels() {
    const visibleZones = getVisibleZones();
    visibleZones.forEach(zone => {
      if (zone.type === 'corner' && zone.props?.name) {
        const midM = (zone.start_m + zone.end_m) / 2;
        const pt = getCoordAtDistance(midM);
        if (pt) {
          const cp = worldToCanvas(pt.x, pt.y);
          ctx.fillStyle = '#e3b341';
          ctx.font = 'bold 11px sans-serif';
          ctx.textAlign = 'center';
          ctx.fillText(`T${zone.props.number || ''} ${zone.props.name}`, cp.x, cp.y - 12);
        }
      }
    });
  }

  function getCoordAtDistance(distance_m) {
    if (!state.circuitData || !state.circuitData.points.length) return null;
    const pts = state.circuitData.points;
    const len = pts.length;
    const totalL = state.circuitData.length_m;

    for (let i = 0; i < len; i++) {
      const pA = pts[i];
      const isLast = i === len - 1;
      const pB = pts[(i + 1) % len];
      const distA = pA.distance_m;
      const distB = isLast ? totalL : pB.distance_m;

      if (distance_m >= distA && distance_m <= distB) {
        const t = (distance_m - distA) / (distB - distA || 1);
        return {
          x: pA.x + t * (pB.x - pA.x),
          y: pA.y + t * (pB.y - pA.y)
        };
      }
    }
    return pts[0];
  }

  // --- Desenho 1D da Linha do Tempo (Régua) ---
  function drawTimeline() {
    const w = dom.timelineCanvas.width;
    const h = dom.timelineCanvas.height;
    timelineCtx.clearRect(0, 0, w, h);

    const totalL = state.circuitData ? state.circuitData.length_m : 5000;
    const toX = (distM) => Math.max(0, Math.min(w, (distM / totalL) * w));

    // Fundo da Régua
    timelineCtx.fillStyle = '#161b22';
    timelineCtx.fillRect(0, 0, w, h);

    // Ticks da Régua
    timelineCtx.strokeStyle = '#30363d';
    timelineCtx.fillStyle = '#8b949e';
    timelineCtx.font = '10px monospace';

    for (let m = 0; m <= totalL; m += 500) {
      const x = toX(m);
      const isMajor = m % 1000 === 0;
      timelineCtx.beginPath();
      timelineCtx.moveTo(x, 0);
      timelineCtx.lineTo(x, isMajor ? 14 : 8);
      timelineCtx.stroke();

      if (isMajor && x > 20 && x < w - 30) {
        timelineCtx.fillText(`${m}m`, x - 14, 22);
      }
    }

    // Faixas de Zonas Stacked (Filtradas)
    const layers = [
      { types: ['sector'], y: 26, height: 8 },
      { types: ['drs_activation', 'drs_detection'], y: 36, height: 8 },
      { types: ['pit_lane', 'pit_entry', 'pit_exit'], y: 46, height: 8 },
      { types: ['braking_zone', 'corner'], y: 56, height: 8 },
    ];

    const visibleZones = getVisibleZones();
    visibleZones.forEach(zone => {
      let layer = layers.find(l => l.types.includes(zone.type));
      if (!layer) layer = layers[3];

      let color = ZONE_COLORS[zone.type] || ZONE_COLORS.default;
      if (zone.type === 'sector') {
        color = ZONE_COLORS[`sector_${zone.props?.number || 1}`] || ZONE_COLORS.sector_1;
      }

      const x0 = toX(zone.start_m);
      const x1 = toX(zone.end_m);

      timelineCtx.fillStyle = color;
      if (zone.start_m === zone.end_m) {
        timelineCtx.fillRect(x0 - 2, layer.y, 4, layer.height);
      } else {
        timelineCtx.fillRect(x0, layer.y, Math.max(2, x1 - x0), layer.height);
      }
    });

    // Destaque do Intervalo Selecionado (em modo edição)
    if (state.interactionMode === 'edit') {
      const selX0 = toX(state.selection.start_m);
      const selX1 = toX(state.selection.end_m);

      timelineCtx.fillStyle = 'rgba(227, 179, 65, 0.25)';
      timelineCtx.strokeStyle = '#e3b341';
      timelineCtx.lineWidth = 1.5;

      if (state.selection.isSinglePoint) {
        timelineCtx.beginPath();
        timelineCtx.moveTo(selX0, 0);
        timelineCtx.lineTo(selX0, h);
        timelineCtx.stroke();
      } else {
        timelineCtx.fillRect(selX0, 0, selX1 - selX0, h);
        timelineCtx.strokeRect(selX0, 0, selX1 - selX0, h);
      }

      drawTimelineHandle(selX0, 'A', '#388bfd');
      if (!state.selection.isSinglePoint) {
        drawTimelineHandle(selX1, 'B', '#f85149');
      }
    }

    // Linha do Cursor Hover
    if (state.hover.isOnTrack) {
      const hx = toX(state.hover.distance_m);
      timelineCtx.strokeStyle = state.interactionMode === 'view' ? '#a371f7' : '#39c5bb';
      timelineCtx.lineWidth = 1.5;
      timelineCtx.beginPath();
      timelineCtx.moveTo(hx, 0);
      timelineCtx.lineTo(hx, h);
      timelineCtx.stroke();
    }
  }

  function drawTimelineHandle(x, letter, color) {
    timelineCtx.save();
    timelineCtx.fillStyle = color;
    timelineCtx.beginPath();
    timelineCtx.moveTo(x - 6, 0);
    timelineCtx.lineTo(x + 6, 0);
    timelineCtx.lineTo(x, 8);
    timelineCtx.closePath();
    timelineCtx.fill();
    timelineCtx.restore();
  }

  function drawAll() {
    drawTrack();
    drawTimeline();
  }

  // --- Gerenciamento do Formulário de Zonas ---
  function renderDynamicPropsForm() {
    const type = dom.selectZoneType.value;
    const container = dom.dynamicPropsContainer;
    container.innerHTML = '';

    const header = document.createElement('div');
    header.className = 'props-header';
    header.textContent = `Atributos para "${type}"`;
    container.appendChild(header);

    const isPointZone = ['drs_detection', 'pit_entry', 'pit_exit'].includes(type);
    dom.checkSinglePoint.checked = isPointZone;
    dom.checkSinglePoint.disabled = isPointZone;
    state.selection.isSinglePoint = isPointZone;
    if (isPointZone) {
      state.selection.end_m = state.selection.start_m;
    }
    updateSelectionUI();

    switch (type) {
      case 'sector':
        container.innerHTML += `
          <div class="form-group">
            <label>Número do Setor:</label>
            <select id="propSectorNumber" class="form-input">
              <option value="1">Setor 1</option>
              <option value="2">Setor 2</option>
              <option value="3">Setor 3</option>
            </select>
          </div>
        `;
        break;

      case 'corner':
        container.innerHTML += `
          <div class="form-row">
            <div class="form-group">
              <label>Número:</label>
              <input type="number" id="propCornerNumber" class="form-input" min="1" value="1">
            </div>
            <div class="form-group">
              <label>Nome Oficial:</label>
              <input type="text" id="propCornerName" class="form-input" placeholder="ex: S do Senna" value="">
            </div>
          </div>
        `;
        break;

      case 'braking_zone':
        container.innerHTML += `
          <div class="form-row">
            <div class="form-group">
              <label>Severidade:</label>
              <select id="propBrakingSeverity" class="form-input">
                <option value="alta">Alta (frenagem forte)</option>
                <option value="media">Média</option>
                <option value="baixa">Baixa</option>
              </select>
            </div>
            <div class="form-group">
              <label>Escapatória (Runoff):</label>
              <select id="propBrakingRunoff" class="form-input">
                <option value="brita">Brita (maior chance SC)</option>
                <option value="asfalto">Asfalto</option>
                <option value="muro">Muro (alto risco)</option>
              </select>
            </div>
          </div>
        `;
        break;

      case 'straight':
        container.innerHTML += `
          <div class="form-group">
            <label>Nome da Reta (opcional):</label>
            <input type="text" id="propStraightName" class="form-input" placeholder="ex: Reta Oposta">
          </div>
        `;
        break;

      case 'pit_lane':
        const defaultSpeed = state.circuitId === 'monaco' ? 60 : 80;
        container.innerHTML += `
          <div class="form-row">
            <div class="form-group">
              <label>Velocidade (km/h):</label>
              <input type="number" id="propPitSpeed" class="form-input" value="${defaultSpeed}" min="40" max="100">
            </div>
            <div class="form-group">
              <label>Perda de Tempo (s):</label>
              <input type="number" step="0.1" id="propPitTimeLoss" class="form-input" value="21.5" min="10" max="40">
            </div>
          </div>
        `;
        break;

      case 'overtaking_spot':
        container.innerHTML += `
          <div class="form-group">
            <label>Dificuldade de Ultrapassagem:</label>
            <select id="propOvertakingDifficulty" class="form-input">
              <option value="baixa">Baixa (fácil passar)</option>
              <option value="media">Média</option>
              <option value="alta">Alta (difícil passar)</option>
            </select>
          </div>
        `;
        break;

      case 'drs_detection':
      case 'drs_activation':
      case 'pit_entry':
      case 'pit_exit':
        container.innerHTML += `
          <div style="font-size: 11px; color: var(--text-muted);">
            Esta zona não requer atributos adicionais no Contrato D4 (props: {}).
          </div>
        `;
        break;
    }
  }

  function getPropsFromForm() {
    const type = dom.selectZoneType.value;
    const props = {};

    switch (type) {
      case 'sector':
        props.number = parseInt(document.getElementById('propSectorNumber')?.value, 10) || 1;
        break;
      case 'corner':
        props.number = parseInt(document.getElementById('propCornerNumber')?.value, 10) || 1;
        props.name = document.getElementById('propCornerName')?.value.trim() || `Curva ${props.number}`;
        break;
      case 'braking_zone':
        props.severity = document.getElementById('propBrakingSeverity')?.value || 'media';
        props.runoff = document.getElementById('propBrakingRunoff')?.value || 'asfalto';
        break;
      case 'straight':
        const name = document.getElementById('propStraightName')?.value.trim();
        if (name) props.name = name;
        break;
      case 'pit_lane':
        props.speed_limit_kmh = parseInt(document.getElementById('propPitSpeed')?.value, 10) || 80;
        props.time_loss_s = parseFloat(document.getElementById('propPitTimeLoss')?.value) || 21.5;
        break;
      case 'overtaking_spot':
        props.difficulty = document.getElementById('propOvertakingDifficulty')?.value || 'media';
        break;
    }
    return props;
  }

  function setFormFromProps(zone) {
    dom.selectZoneType.value = zone.type;
    renderDynamicPropsForm();

    const p = zone.props || {};
    switch (zone.type) {
      case 'sector':
        if (document.getElementById('propSectorNumber')) {
          document.getElementById('propSectorNumber').value = p.number || 1;
        }
        break;
      case 'corner':
        if (document.getElementById('propCornerNumber')) document.getElementById('propCornerNumber').value = p.number || 1;
        if (document.getElementById('propCornerName')) document.getElementById('propCornerName').value = p.name || '';
        break;
      case 'braking_zone':
        if (document.getElementById('propBrakingSeverity')) document.getElementById('propBrakingSeverity').value = p.severity || 'media';
        if (document.getElementById('propBrakingRunoff')) document.getElementById('propBrakingRunoff').value = p.runoff || 'asfalto';
        break;
      case 'straight':
        if (document.getElementById('propStraightName')) document.getElementById('propStraightName').value = p.name || '';
        break;
      case 'pit_lane':
        if (document.getElementById('propPitSpeed')) document.getElementById('propPitSpeed').value = p.speed_limit_kmh || 80;
        if (document.getElementById('propPitTimeLoss')) document.getElementById('propPitTimeLoss').value = p.time_loss_s || 21.5;
        break;
      case 'overtaking_spot':
        if (document.getElementById('propOvertakingDifficulty')) document.getElementById('propOvertakingDifficulty').value = p.difficulty || 'media';
        break;
    }
  }

  // --- CRUD de Zonas ---
  function saveZone() {
    let start_m = parseFloat(dom.inputStartM.value) || 0;
    let end_m = parseFloat(dom.inputEndM.value) || 0;
    const type = dom.selectZoneType.value;
    const isPointZone = ['drs_detection', 'pit_entry', 'pit_exit'].includes(type) || state.selection.isSinglePoint;

    if (isPointZone) {
      end_m = start_m;
    } else if (start_m > end_m) {
      const tmp = start_m;
      start_m = end_m;
      end_m = tmp;
    }

    const props = getPropsFromForm();

    if (state.editingZoneId) {
      const idx = state.zones.findIndex(z => z.id === state.editingZoneId);
      if (idx !== -1) {
        state.zones[idx] = {
          ...state.zones[idx],
          type,
          start_m,
          end_m,
          props,
        };
      }
      cancelEdit();
    } else {
      const newZone = {
        id: 'zone_' + Date.now() + '_' + Math.random().toString(36).substring(2, 6),
        type,
        start_m,
        end_m,
        props,
      };
      state.zones.push(newZone);
    }

    state.zones.sort((a, b) => a.start_m - b.start_m);

    renderZonesList();
    validateD4Schema();
    drawAll();
  }

  function editZone(id) {
    const zone = state.zones.find(z => z.id === id);
    if (!zone) return;

    state.editingZoneId = id;
    dom.formModeTitle.textContent = 'Editar Zona';
    dom.btnSaveZone.textContent = '💾 Salvar Alterações';
    dom.btnCancelEdit.style.display = 'inline-flex';

    state.selection.start_m = zone.start_m;
    state.selection.end_m = zone.end_m;
    state.selection.isSinglePoint = (zone.start_m === zone.end_m);

    updateSelectionUI();
    setFormFromProps(zone);
    state.viewOptions.selectedZoneId = id;
    drawAll();
  }

  function cancelEdit() {
    state.editingZoneId = null;
    dom.formModeTitle.textContent = 'Anotar Nova Zona';
    dom.btnSaveZone.textContent = '➕ Adicionar Zona';
    dom.btnCancelEdit.style.display = 'none';
    state.viewOptions.selectedZoneId = null;
    drawAll();
  }

  function deleteZone(id) {
    state.zones = state.zones.filter(z => z.id !== id);
    if (state.editingZoneId === id) {
      cancelEdit();
    }
    renderZonesList();
    validateD4Schema();
    drawAll();
  }

  // --- Renderização da Lista de Zonas ---
  function renderZonesList() {
    const container = dom.zonesListContainer;
    container.innerHTML = '';
    
    const filtered = getVisibleZones();
    dom.zonesCount.textContent = state.zones.length;

    if (!filtered.length) {
      container.innerHTML = `
        <div style="padding: 16px; text-align: center; color: var(--text-dim); font-size: 12px;">
          Nenhuma zona cadastrada neste filtro.
        </div>
      `;
      return;
    }

    filtered.forEach(zone => {
      const card = document.createElement('div');
      card.className = `zone-card ${state.viewOptions.selectedZoneId === zone.id ? 'selected' : ''}`;
      card.id = `card_${zone.id}`;
      card.dataset.id = zone.id;

      let color = ZONE_COLORS[zone.type] || ZONE_COLORS.default;
      if (zone.type === 'sector') {
        color = ZONE_COLORS[`sector_${zone.props?.number || 1}`] || ZONE_COLORS.sector_1;
      }
      card.style.borderLeftColor = color;

      let propsSummary = '';
      if (zone.type === 'sector') propsSummary = `Setor ${zone.props?.number || 1}`;
      else if (zone.type === 'corner') propsSummary = `T${zone.props?.number || ''}: ${zone.props?.name || ''}`;
      else if (zone.type === 'braking_zone') propsSummary = `${zone.props?.severity || ''} | ${zone.props?.runoff || ''}`;
      else if (zone.type === 'pit_lane') propsSummary = `${zone.props?.speed_limit_kmh}km/h | +${zone.props?.time_loss_s}s`;
      else if (zone.type === 'straight') propsSummary = zone.props?.name || '';
      else if (zone.type === 'overtaking_spot') propsSummary = `Dif: ${zone.props?.difficulty || 'media'}`;

      const delta = Math.round((zone.end_m - zone.start_m) * 10) / 10;
      const rangeText = (zone.start_m === zone.end_m) 
        ? `${zone.start_m} m (Ponto)` 
        : `${zone.start_m} → ${zone.end_m} m (${delta} m)`;

      card.innerHTML = `
        <div class="zone-card-info">
          <div class="zone-card-top">
            <span class="zone-badge ${zone.type}">${zone.type}</span>
            <span class="zone-range">${rangeText}</span>
          </div>
          ${propsSummary ? `<span class="zone-props-summary">${propsSummary}</span>` : ''}
        </div>
        <div class="zone-card-actions">
          <button class="btn-icon edit" title="Editar Zona">✏️</button>
          <button class="btn-icon delete" title="Remover Zona">🗑️</button>
        </div>
      `;

      card.addEventListener('mouseenter', () => {
        state.viewOptions.selectedZoneId = zone.id;
        drawAll();
      });

      card.addEventListener('mouseleave', () => {
        if (state.editingZoneId !== zone.id) {
          state.viewOptions.selectedZoneId = null;
          drawAll();
        }
      });

      card.querySelector('.edit').addEventListener('click', (e) => {
        e.stopPropagation();
        editZone(zone.id);
      });

      card.querySelector('.delete').addEventListener('click', (e) => {
        e.stopPropagation();
        deleteZone(zone.id);
      });

      container.appendChild(card);
    });
  }

  // --- Validação Rigorosa do Contrato D4 ---
  function validateD4Schema() {
    const issues = [];
    const totalL = state.circuitData ? state.circuitData.length_m : 0;

    // Regra 1: Geral
    if (!totalL || totalL <= 0) {
      issues.push({ level: 'fail', title: 'Comprimento Inválido', desc: 'length_m deve ser maior que 0.' });
    }

    // Regra 2: Limites espaciais e ordem
    state.zones.forEach((z, i) => {
      if (z.start_m < 0 || z.start_m > totalL || z.end_m < 0 || z.end_m > totalL) {
        issues.push({
          level: 'fail',
          title: `Zona #${i + 1} (${z.type}) Fora dos Limites`,
          desc: `Intervalo [${z.start_m}, ${z.end_m}] excede [0, ${totalL}].`
        });
      }
      if (z.start_m > z.end_m) {
        issues.push({
          level: 'fail',
          title: `Zona #${i + 1} Invertida`,
          desc: `start_m (${z.start_m}) maior que end_m (${z.end_m}).`
        });
      }
    });

    // Regra 3: Zonas Pontuais
    const pointTypes = ['drs_detection', 'pit_entry', 'pit_exit'];
    state.zones.forEach((z, i) => {
      if (pointTypes.includes(z.type) && z.start_m !== z.end_m) {
        issues.push({
          level: 'fail',
          title: `Zona Pontual Inválida #${i + 1}`,
          desc: `${z.type} deve ter largura zero (start_m == end_m). Encontrado: [${z.start_m}, ${z.end_m}].`
        });
      }
    });

    // Regra 4: Zonas de Intervalo
    const intervalTypes = ['sector', 'corner', 'braking_zone', 'straight', 'drs_activation', 'pit_lane'];
    state.zones.forEach((z, i) => {
      if (intervalTypes.includes(z.type) && z.start_m === z.end_m) {
        issues.push({
          level: 'fail',
          title: `Zona de Intervalo Vazia #${i + 1}`,
          desc: `${z.type} requer intervalo real (start_m < end_m).`
        });
      }
    });

    // Regra 5: Setores contínuos e sem sobreposição cobrindo 100%
    const sectors = state.zones.filter(z => z.type === 'sector').sort((a, b) => a.start_m - b.start_m);
    if (sectors.length !== 3) {
      issues.push({
        level: 'fail',
        title: 'Setores Incompletos',
        desc: `Devem existir exatamente 3 setores (encontrados: ${sectors.length}).`
      });
    } else {
      if (sectors[0].start_m !== 0) {
        issues.push({ level: 'fail', title: 'Setor 1 Incorreto', desc: `Setor 1 deve começar em 0m (começa em ${sectors[0].start_m}m).` });
      }
      if (sectors[0].end_m !== sectors[1].start_m) {
        issues.push({ level: 'fail', title: 'Lacuna/Sobreposição S1 e S2', desc: `Fim do S1 (${sectors[0].end_m}m) != Início do S2 (${sectors[1].start_m}m).` });
      }
      if (sectors[1].end_m !== sectors[2].start_m) {
        issues.push({ level: 'fail', title: 'Lacuna/Sobreposição S2 e S3', desc: `Fim do S2 (${sectors[1].end_m}m) != Início do S3 (${sectors[2].start_m}m).` });
      }
      if (sectors[2].end_m !== totalL) {
        issues.push({ level: 'fail', title: 'Setor 3 Incorreto', desc: `Setor 3 deve terminar em ${totalL}m (termina em ${sectors[2].end_m}m).` });
      }
    }

    // Regra 6: Presença Mínima Obrigatoria
    const hasDrsDet = state.zones.some(z => z.type === 'drs_detection');
    const hasDrsAct = state.zones.some(z => z.type === 'drs_activation');
    const hasPitEntry = state.zones.some(z => z.type === 'pit_entry');
    const hasPitLane = state.zones.some(z => z.type === 'pit_lane');
    const hasPitExit = state.zones.some(z => z.type === 'pit_exit');
    const hasBraking = state.zones.some(z => z.type === 'braking_zone');

    if (!hasDrsDet || !hasDrsAct) issues.push({ level: 'warn', title: 'Zonas de DRS Ausentes', desc: 'Circuito deve possuir detecção e ativação de DRS.' });
    if (!hasPitEntry || !hasPitLane || !hasPitExit) issues.push({ level: 'warn', title: 'Estrutura de Boxes Ausente', desc: 'Circuito deve possuir pit_entry, pit_lane e pit_exit.' });
    if (!hasBraking) issues.push({ level: 'warn', title: 'Frenagens Ausentes', desc: 'Circuito deve possuir as principais zonas de frenagem marcadas.' });

    // Atualizar UI do Badge
    const failures = issues.filter(i => i.level === 'fail');
    const warnings = issues.filter(i => i.level === 'warn');

    if (failures.length === 0 && warnings.length === 0) {
      dom.validationStatusBadge.className = 'validation-badge valid';
      dom.validationIcon.textContent = '✓';
      dom.validationText.textContent = 'Schema D4 Válido';
    } else if (failures.length > 0) {
      dom.validationStatusBadge.className = 'validation-badge invalid';
      dom.validationIcon.textContent = '✕';
      dom.validationText.textContent = `${failures.length} Erro(s) no Schema`;
    } else {
      dom.validationStatusBadge.className = 'validation-badge invalid';
      dom.validationStatusBadge.style.backgroundColor = 'rgba(227, 179, 65, 0.15)';
      dom.validationStatusBadge.style.color = '#e3b341';
      dom.validationIcon.textContent = '⚠';
      dom.validationText.textContent = `${warnings.length} Aviso(s) D4`;
    }

    state.validationIssues = issues;
  }

  function showValidationModal() {
    const body = dom.validationModalBody;
    body.innerHTML = '';

    if (!state.validationIssues || !state.validationIssues.length) {
      body.innerHTML = `
        <div class="rule-check-item pass">
          <div class="rule-icon">✓</div>
          <div class="rule-desc">
            <div class="rule-title">Tudo Válido Conforme Contrato D4!</div>
            <div class="rule-detail">Nenhuma inconsistência lógica, sobreposição indevida ou limite excedido.</div>
          </div>
        </div>
      `;
    } else {
      state.validationIssues.forEach(item => {
        body.innerHTML += `
          <div class="rule-check-item ${item.level}">
            <div class="rule-icon">${item.level === 'fail' ? '✕' : '⚠'}</div>
            <div class="rule-desc">
              <div class="rule-title">${item.title}</div>
              <div class="rule-detail">${item.desc}</div>
            </div>
          </div>
        `;
      });
    }

    dom.validationModal.classList.remove('hidden');
  }

  // --- Exportação e Salvamento Direto ---
  function buildD4Payload() {
    const cleanZones = state.zones.map(z => ({
      type: z.type,
      start_m: Math.round(z.start_m * 10) / 10,
      end_m: Math.round(z.end_m * 10) / 10,
      props: z.props || {},
    }));

    return {
      circuit_id: state.circuitData.circuit_id,
      length_m: state.circuitData.length_m,
      points: state.circuitData.points,
      zones: cleanZones,
    };
  }

  function saveDirectlyToDisk() {
    if (!state.circuitData) return;

    validateD4Schema();
    const failures = state.validationIssues.filter(i => i.level === 'fail');
    if (failures.length > 0) {
      if (!confirm(`Atenção: Existem ${failures.length} erros de validação no Schema D4.\nDeseja salvar mesmo assim?`)) {
        showValidationModal();
        return;
      }
    }

    const payload = buildD4Payload();

    fetch(`/api/track-maps/${state.circuitData.circuit_id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(result => {
        alert(`✅ Sucesso! Arquivo gravado diretamente em:\n${result.path}\n(${state.zones.length} zonas salvas)`);
      })
      .catch(err => {
        console.warn('API não acessível (rodando offline?), gerando download:', err);
        if (confirm('Servidor de API não respondeu (você está rodando via file:// sem Docker?).\nDeseja baixar o arquivo JSON via download no seu navegador?')) {
          exportD4JSON();
        }
      });
  }

  function exportD4JSON() {
    if (!state.circuitData) return;

    validateD4Schema();
    const failures = state.validationIssues.filter(i => i.level === 'fail');
    if (failures.length > 0) {
      if (!confirm(`Atenção: Existem ${failures.length} erros de validação no Schema D4.\nDeseja exportar mesmo assim?`)) {
        showValidationModal();
        return;
      }
    }

    const d4Object = buildD4Payload();
    const jsonStr = JSON.stringify(d4Object, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${state.circuitData.circuit_id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function handleD4Import(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const data = JSON.parse(e.target.result);
        if (!data.circuit_id || !data.length_m || !Array.isArray(data.points)) {
          alert('Arquivo inválido: JSON não contém a estrutura esperada do Contrato D4.');
          return;
        }

        state.circuitData = data;
        state.circuitId = data.circuit_id;
        dom.circuitSelect.value = data.circuit_id;

        state.zones = (data.zones || []).map((z, idx) => ({
          id: 'zone_' + Date.now() + '_' + idx,
          type: z.type,
          start_m: z.start_m,
          end_m: z.end_m,
          props: z.props || {}
        }));

        onCircuitLoaded();
        alert(`Arquivo D4 carregado com sucesso! (${state.zones.length} zonas importadas)`);
      } catch (err) {
        alert('Erro ao ler JSON: ' + err.message);
      }
    };
    reader.readAsText(file);
  }

  function handleD3Load(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const data = JSON.parse(e.target.result);
        if (!data.circuit_id || !data.length_m || !Array.isArray(data.points)) {
          alert('Arquivo D3 inválido: Esperado { circuit_id, length_m, points }.');
          return;
        }
        state.circuitData = data;
        state.circuitId = data.circuit_id;
        state.zones = [];
        onCircuitLoaded();
        alert(`Polyline D3 carregada: ${data.points.length} pontos.`);
      } catch (err) {
        alert('Erro ao ler JSON: ' + err.message);
      }
    };
    reader.readAsText(file);
  }

  // --- UI e Sincronização de Seleção ---
  function updateSelectionUI() {
    dom.inputStartM.value = state.selection.start_m;
    dom.inputEndM.value = state.selection.end_m;

    const delta = state.selection.isSinglePoint 
      ? 0 
      : Math.max(0, Math.round((state.selection.end_m - state.selection.start_m) * 10) / 10);
    dom.selectionDeltaText.textContent = `${delta} m`;

    dom.pointModeBadge.textContent = state.selection.isSinglePoint ? 'Modo Pontual (start == end)' : 'Modo Intervalo';
    dom.pointModeBadge.style.color = state.selection.isSinglePoint ? 'var(--accent-cyan)' : 'var(--accent-gold)';

    if (state.circuitData) {
      dom.timelineLengthMeta.textContent = `${state.selection.start_m}m ➔ ${state.selection.end_m}m / ${state.circuitData.length_m}m`;
    }
  }

  function updateHUD(hoverData) {
    if (!hoverData || !hoverData.isOnTrack) {
      if (dom.hudOverlay) dom.hudOverlay.style.opacity = '0.5';
      return;
    }
    if (dom.hudOverlay) dom.hudOverlay.style.opacity = '1';
    dom.hudDistance.textContent = `${hoverData.distance_m.toFixed(1)} m`;
    dom.hudPointIndex.textContent = `#${hoverData.pointIndex} / ${state.circuitData ? state.circuitData.points.length : 0}`;
    dom.hudCoords.textContent = `${hoverData.x.toFixed(1)}, ${hoverData.y.toFixed(1)}`;

    const active = state.zones.filter(z => hoverData.distance_m >= z.start_m && hoverData.distance_m <= z.end_m);
    if (active.length > 0) {
      dom.hudActiveZones.textContent = active.map(z => {
        if (z.type === 'sector') return `Setor ${z.props?.number || 1}`;
        if (z.type === 'corner') return `T${z.props?.number || ''}: ${z.props?.name || ''}`;
        return z.type;
      }).join(' | ');
    } else {
      dom.hudActiveZones.textContent = 'nenhuma';
    }
  }

  function handleResize() {
    const rect = dom.canvasContainer.getBoundingClientRect();
    dom.trackCanvas.width = rect.width;
    dom.trackCanvas.height = rect.height;

    const tlRect = dom.timelineCanvas.parentElement.getBoundingClientRect();
    dom.timelineCanvas.width = tlRect.width;
    dom.timelineCanvas.height = tlRect.height;

    drawAll();
  }

  // --- Event Listeners ---
  function setupEventListeners() {
    window.addEventListener('resize', handleResize);

    // Alternador de Modo (Anotação vs Inspeção)
    dom.btnModeEdit.addEventListener('click', () => {
      state.interactionMode = 'edit';
      dom.btnModeEdit.className = 'btn btn-sm btn-primary';
      dom.btnModeView.className = 'btn btn-sm';
      dom.trackCanvas.style.cursor = 'crosshair';
      drawAll();
    });

    dom.btnModeView.addEventListener('click', () => {
      state.interactionMode = 'view';
      dom.btnModeView.className = 'btn btn-sm btn-primary';
      dom.btnModeEdit.className = 'btn btn-sm';
      dom.trackCanvas.style.cursor = 'pointer';
      drawAll();
    });

    // Seletor de Circuito
    dom.circuitSelect.addEventListener('change', (e) => {
      loadCircuit(e.target.value);
    });

    // Botões de Arquivo e Salvamento
    dom.btnLoadD3.addEventListener('click', () => dom.d3FileInput.click());
    dom.d3FileInput.addEventListener('change', (e) => {
      if (e.target.files.length) handleD3Load(e.target.files[0]);
    });

    dom.btnImportD4.addEventListener('click', () => dom.d4FileInput.click());
    dom.d4FileInput.addEventListener('change', (e) => {
      if (e.target.files.length) handleD4Import(e.target.files[0]);
    });

    dom.btnSaveToDisk.addEventListener('click', saveDirectlyToDisk);
    dom.btnExportD4.addEventListener('click', exportD4JSON);

    // Modal de Validação
    dom.validationStatusBadge.addEventListener('click', showValidationModal);
    dom.btnCloseValidationModal.addEventListener('click', () => dom.validationModal.classList.add('hidden'));
    dom.btnOkValidationModal.addEventListener('click', () => dom.validationModal.classList.add('hidden'));

    // Toolbar 2D
    dom.btnZoomIn.addEventListener('click', () => {
      state.viewport.zoom = Math.min(6, state.viewport.zoom * 1.25);
      drawAll();
    });
    dom.btnZoomOut.addEventListener('click', () => {
      state.viewport.zoom = Math.max(0.4, state.viewport.zoom / 1.25);
      drawAll();
    });
    dom.btnResetView.addEventListener('click', () => {
      resetViewport();
      drawAll();
    });
    dom.btnTogglePoints.addEventListener('click', () => {
      state.viewOptions.showPoints = !state.viewOptions.showPoints;
      dom.btnTogglePoints.classList.toggle('btn-primary', state.viewOptions.showPoints);
      drawAll();
    });
    dom.btnToggleLabels.addEventListener('click', () => {
      state.viewOptions.showLabels = !state.viewOptions.showLabels;
      dom.btnToggleLabels.classList.toggle('btn-primary', state.viewOptions.showLabels);
      drawAll();
    });

    // Interação do Mouse no Canvas 2D
    dom.trackCanvas.addEventListener('mousedown', (e) => {
      if (e.button === 1 || e.altKey || e.shiftKey) {
        state.viewport.isDragging = true;
        state.viewport.dragStartX = e.clientX - state.viewport.panX;
        state.viewport.dragStartY = e.clientY - state.viewport.panY;
        dom.trackCanvas.style.cursor = 'grabbing';
      } else if (e.button === 0) {
        const rect = dom.trackCanvas.getBoundingClientRect();
        const world = canvasToWorld(e.clientX - rect.left, e.clientY - rect.top);
        const pt = findClosestTrackPoint(world.x, world.y);

        if (pt) {
          if (state.interactionMode === 'view') {
            // Modo Visualização: encontra zonas nesta distância e seleciona na lista
            const matching = state.zones.filter(z => pt.distance_m >= z.start_m && pt.distance_m <= z.end_m);
            if (matching.length > 0) {
              const targetZone = matching[0];
              state.viewOptions.selectedZoneId = targetZone.id;
              
              // Rolar lista até o card correspondente
              const card = document.getElementById(`card_${targetZone.id}`);
              if (card) {
                card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
              }
            } else {
              state.viewOptions.selectedZoneId = null;
            }
            drawAll();
          } else {
            // Modo Anotação: define intervalo A/B
            if (state.selection.isSinglePoint) {
              state.selection.start_m = pt.distance_m;
              state.selection.end_m = pt.distance_m;
            } else {
              if (state.selection.activePointTarget === 'start') {
                state.selection.start_m = pt.distance_m;
                if (state.selection.start_m > state.selection.end_m) {
                  state.selection.end_m = Math.min(state.circuitData.length_m, pt.distance_m + 100);
                }
                state.selection.activePointTarget = 'end';
              } else {
                state.selection.end_m = pt.distance_m;
                if (state.selection.end_m < state.selection.start_m) {
                  const tmp = state.selection.start_m;
                  state.selection.start_m = state.selection.end_m;
                  state.selection.end_m = tmp;
                }
                state.selection.activePointTarget = 'start';
              }
            }
            updateSelectionUI();
            drawAll();
          }
        }
      }
    });

    window.addEventListener('mousemove', (e) => {
      if (state.viewport.isDragging) {
        state.viewport.panX = e.clientX - state.viewport.dragStartX;
        state.viewport.panY = e.clientY - state.viewport.dragStartY;
        drawAll();
      }
    });

    window.addEventListener('mouseup', () => {
      if (state.viewport.isDragging) {
        state.viewport.isDragging = false;
        dom.trackCanvas.style.cursor = state.interactionMode === 'view' ? 'pointer' : 'crosshair';
      }
    });

    dom.trackCanvas.addEventListener('mousemove', (e) => {
      const rect = dom.trackCanvas.getBoundingClientRect();
      const world = canvasToWorld(e.clientX - rect.left, e.clientY - rect.top);
      const pt = findClosestTrackPoint(world.x, world.y);

      if (pt) {
        state.hover = {
          distance_m: pt.distance_m,
          pointIndex: pt.pointIndex,
          x: pt.x,
          y: pt.y,
          isOnTrack: true,
        };
      } else {
        state.hover.isOnTrack = false;
      }
      updateHUD(state.hover);
      drawAll();
    });

    dom.trackCanvas.addEventListener('mouseleave', () => {
      state.hover.isOnTrack = false;
      updateHUD(state.hover);
      drawAll();
    });

    dom.trackCanvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;
      state.viewport.zoom = Math.max(0.4, Math.min(8, state.viewport.zoom * zoomFactor));
      drawAll();
    });

    // Interação com a Régua 1D (Timeline)
    dom.timelineCanvas.addEventListener('mousedown', (e) => {
      const rect = dom.timelineCanvas.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const totalL = state.circuitData ? state.circuitData.length_m : 5000;
      const distM = Math.round(((clickX / rect.width) * totalL) * 10) / 10;

      if (state.interactionMode === 'view') {
        const matching = state.zones.filter(z => distM >= z.start_m && distM <= z.end_m);
        if (matching.length > 0) {
          state.viewOptions.selectedZoneId = matching[0].id;
          const card = document.getElementById(`card_${matching[0].id}`);
          if (card) card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } else {
          state.viewOptions.selectedZoneId = null;
        }
      } else {
        if (state.selection.isSinglePoint) {
          state.selection.start_m = distM;
          state.selection.end_m = distM;
        } else {
          const distToA = Math.abs(distM - state.selection.start_m);
          const distToB = Math.abs(distM - state.selection.end_m);

          if (distToA < distToB) {
            state.selection.start_m = distM;
          } else {
            state.selection.end_m = distM;
          }
          if (state.selection.start_m > state.selection.end_m) {
            const tmp = state.selection.start_m;
            state.selection.start_m = state.selection.end_m;
            state.selection.end_m = tmp;
          }
        }
        updateSelectionUI();
      }
      drawAll();
    });

    // Inputs Numéricos de Seleção
    dom.inputStartM.addEventListener('input', () => {
      state.selection.start_m = Math.max(0, parseFloat(dom.inputStartM.value) || 0);
      if (state.selection.isSinglePoint) state.selection.end_m = state.selection.start_m;
      updateSelectionUI();
      drawAll();
    });

    dom.inputEndM.addEventListener('input', () => {
      state.selection.end_m = Math.max(0, parseFloat(dom.inputEndM.value) || 0);
      if (state.selection.isSinglePoint) state.selection.start_m = state.selection.end_m;
      updateSelectionUI();
      drawAll();
    });

    dom.btnStartMinus10.addEventListener('click', () => {
      state.selection.start_m = Math.max(0, state.selection.start_m - 10);
      if (state.selection.isSinglePoint) state.selection.end_m = state.selection.start_m;
      updateSelectionUI();
      drawAll();
    });
    dom.btnStartPlus10.addEventListener('click', () => {
      state.selection.start_m = Math.min(state.circuitData?.length_m || 5000, state.selection.start_m + 10);
      if (state.selection.isSinglePoint) state.selection.end_m = state.selection.start_m;
      updateSelectionUI();
      drawAll();
    });
    dom.btnEndMinus10.addEventListener('click', () => {
      state.selection.end_m = Math.max(0, state.selection.end_m - 10);
      if (state.selection.isSinglePoint) state.selection.start_m = state.selection.end_m;
      updateSelectionUI();
      drawAll();
    });
    dom.btnEndPlus10.addEventListener('click', () => {
      state.selection.end_m = Math.min(state.circuitData?.length_m || 5000, state.selection.end_m + 10);
      if (state.selection.isSinglePoint) state.selection.start_m = state.selection.end_m;
      updateSelectionUI();
      drawAll();
    });

    dom.checkSinglePoint.addEventListener('change', (e) => {
      state.selection.isSinglePoint = e.target.checked;
      if (state.selection.isSinglePoint) state.selection.end_m = state.selection.start_m;
      updateSelectionUI();
      drawAll();
    });

    dom.selectZoneType.addEventListener('change', renderDynamicPropsForm);
    dom.btnSaveZone.addEventListener('click', saveZone);
    dom.btnCancelEdit.addEventListener('click', cancelEdit);

    dom.btnClearAllZones.addEventListener('click', () => {
      if (state.zones.length === 0) return;
      if (confirm('Tem certeza que deseja remover todas as zonas anotadas deste circuito?')) {
        state.zones = [];
        cancelEdit();
        renderZonesList();
        validateD4Schema();
        drawAll();
      }
    });

    // Filtros Rápidos (Sincronizados com a lista e com a renderização visual do mapa e da régua)
    dom.filterChips.forEach(chip => {
      chip.addEventListener('click', () => {
        dom.filterChips.forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        state.activeFilter = chip.dataset.filter;
        renderZonesList();
        drawAll(); // Atualiza mapa 2D e régua 1D imediatamente!
      });
    });
  }

  // Iniciar
  window.addEventListener('DOMContentLoaded', init);

})();
