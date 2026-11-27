import React, {
  useEffect,
  useRef,
  useState,
  useCallback,
  useMemo,
} from "react";
import {
  EnrichedDriverState,
  TrackMapData,
  CircuitPoint,
  TrackStatus,
} from "@/types";
import { getTrackMap } from "@/lib/api";
import { TYRE_INFO, formatLapTime, formatGap } from "@/lib/constants";
import {
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Tag,
  Flag,
  Zap,
  X,
  Layers,
} from "lucide-react";

interface CircuitCanvasProps {
  circuitId: string;
  circuitName?: string;
  drivers: EnrichedDriverState[];
  trackStatus?: TrackStatus;
  selectedDriverId?: string | null;
  onSelectDriver?: (driverId: string | null) => void;
  className?: string;
}

interface ViewTransform {
  scale: number;
  offsetX: number;
  offsetY: number;
  userScale: number;
  panX: number;
  panY: number;
}

export const CircuitCanvas: React.FC<CircuitCanvasProps> = ({
  circuitId,
  circuitName = "Circuito",
  drivers,
  trackStatus = "GREEN",
  selectedDriverId,
  onSelectDriver,
  className = "",
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Dados do traçado
  const [trackData, setTrackData] = useState<TrackMapData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Opções de visualização da pista
  const [showTags, setShowTags] = useState<boolean>(true);
  const [showCorners, setShowCorners] = useState<boolean>(true);
  const [showDRSZones, setShowDRSZones] = useState<boolean>(true);
  const [showSectors, setShowSectors] = useState<boolean>(true);

  // Interatividade (Hover e Pan)
  const [hoveredDriver, setHoveredDriver] =
    useState<EnrichedDriverState | null>(null);
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(
    null,
  );
  const [isPanning, setIsPanning] = useState<boolean>(false);
  const [startPan, setStartPan] = useState<{ x: number; y: number }>({
    x: 0,
    y: 0,
  });
  const [userPan, setUserPan] = useState<{ x: number; y: number }>({
    x: 0,
    y: 0,
  });
  const [userZoom, setUserZoom] = useState<number>(1.0);

  // Referências para valores dinâmicos: evita destruir/recriar o rAF a cada tick do WebSocket ou hover
  const driversRef = useRef(drivers);
  driversRef.current = drivers;

  const hoveredDriverRef = useRef(hoveredDriver);
  hoveredDriverRef.current = hoveredDriver;

  const selectedDriverIdRef = useRef(selectedDriverId);
  selectedDriverIdRef.current = selectedDriverId;

  const userZoomRef = useRef(userZoom);
  userZoomRef.current = userZoom;

  const userPanRef = useRef(userPan);
  userPanRef.current = userPan;

  const viewOptionsRef = useRef({
    showTags,
    showCorners,
    showDRSZones,
    showSectors,
  });
  viewOptionsRef.current = {
    showTags,
    showCorners,
    showDRSZones,
    showSectors,
  };

  // Posições animadas suavizadas dos carros (distância interpolada continuamente a 60fps)
  const animDistancesRef = useRef<Record<string, number>>({});
  const lastTimestampRef = useRef<number>(performance.now());
  const animationFrameIdRef = useRef<number | null>(null);

  // Carrega a geometria do circuito
  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setError(null);

    getTrackMap(circuitId)
      .then((data) => {
        if (!isMounted) return;
        setTrackData(data);
        setLoading(false);
      })
      .catch((err) => {
        if (!isMounted) return;
        console.error(
          `[CircuitCanvas] Falha ao carregar mapa de ${circuitId}:`,
          err,
        );
        setError("Não foi possível carregar a geometria da pista.");
        setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [circuitId]);

  // Bounding box e limites da pista
  const trackBounds = useMemo(() => {
    if (!trackData || !trackData.points || trackData.points.length === 0) {
      return {
        minX: 0,
        maxX: 100,
        minY: 0,
        maxY: 100,
        width: 100,
        height: 100,
      };
    }

    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;

    for (const p of trackData.points) {
      if (p.x < minX) minX = p.x;
      if (p.x > maxX) maxX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.y > maxY) maxY = p.y;
    }

    const width = maxX - minX || 1;
    const height = maxY - minY || 1;

    return { minX, maxX, minY, maxY, width, height };
  }, [trackData]);

  // Função utilitária para interpolar ponto (x, y) e ângulo tangente a partir de distance_m
  const getPointAtDistance = useCallback(
    (
      distance: number,
      points: CircuitPoint[],
      totalLength: number,
    ): { x: number; y: number; angle: number } => {
      if (!points || points.length === 0) {
        return { x: 0, y: 0, angle: 0 };
      }

      // Normaliza a distância para o loop da pista
      let d = distance % totalLength;
      if (d < 0) d += totalLength;

      // Busca o segmento que contém a distância
      let p1 = points[0];
      let p2 = points[points.length - 1];

      for (let i = 0; i < points.length - 1; i++) {
        if (d >= points[i].distance_m && d <= points[i + 1].distance_m) {
          p1 = points[i];
          p2 = points[i + 1];
          break;
        }
      }

      // Caso especial da linha de chegada (último ponto para o primeiro)
      if (d > points[points.length - 1].distance_m) {
        p1 = points[points.length - 1];
        p2 = points[0];
      }

      const segmentSpan =
        p2.distance_m >= p1.distance_m
          ? p2.distance_m - p1.distance_m || 1
          : totalLength - p1.distance_m + p2.distance_m || 1;

      const segD =
        d >= p1.distance_m
          ? d - p1.distance_m
          : totalLength - p1.distance_m + d;
      const t = Math.max(0, Math.min(1, segD / segmentSpan));

      const x = p1.x + t * (p2.x - p1.x);
      const y = p1.y + t * (p2.y - p1.y);
      const angle = Math.atan2(p2.y - p1.y, p2.x - p1.x);

      return { x, y, angle };
    },
    [],
  );

  // Converte coordenadas reais do circuito para coordenadas de tela do Canvas
  const worldToCanvas = useCallback(
    (
      worldX: number,
      worldY: number,
      canvasWidth: number,
      canvasHeight: number,
      transform: ViewTransform,
    ): { x: number; y: number } => {
      const { minX, maxY } = trackBounds;
      // Inverte Y para corresponder ao sistema cartesiano tradicional das coordenadas FastF1
      const normalizedX = (worldX - minX) * transform.scale;
      const normalizedY = (maxY - worldY) * transform.scale;

      const screenX =
        canvasWidth / 2 +
        (normalizedX - (canvasWidth / 2 - transform.offsetX)) *
          transform.userScale +
        transform.panX;
      const screenY =
        canvasHeight / 2 +
        (normalizedY - (canvasHeight / 2 - transform.offsetY)) *
          transform.userScale +
        transform.panY;

      return { x: screenX, y: screenY };
    },
    [trackBounds],
  );

  // Atualização e renderização do loop Canvas 2D
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !trackData || trackData.points.length === 0) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let isRunning = true;

    const render = (now: number) => {
      if (!isRunning) return;

      const deltaTime = Math.min(0.1, (now - lastTimestampRef.current) / 1000);
      lastTimestampRef.current = now;

      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const width = rect.width;
      const height = rect.height;

      if (width === 0 || height === 0) {
        animationFrameIdRef.current = requestAnimationFrame(render);
        return;
      }

      // Ajusta dimensões do buffer para nitidez de tela de alta resolução
      if (
        canvas.width !== Math.floor(width * dpr) ||
        canvas.height !== Math.floor(height * dpr)
      ) {
        canvas.width = Math.floor(width * dpr);
        canvas.height = Math.floor(height * dpr);
      }

      ctx.save();
      ctx.scale(dpr, dpr);

      // Limpa fundo
      ctx.fillStyle = "#0c1017";
      ctx.fillRect(0, 0, width, height);

      // Grade sutil de fundo estilo telemetria F1
      ctx.strokeStyle = "rgba(30, 41, 59, 0.4)";
      ctx.lineWidth = 1;
      const gridSize = 40;
      for (let x = 0; x < width; x += gridSize) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
      for (let y = 0; y < height; y += gridSize) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }

      // Calcula escala para enquadrar a pista perfeitamente com padding
      const padding = 60;
      const availableW = Math.max(10, width - padding * 2);
      const availableH = Math.max(10, height - padding * 2);

      const scaleX = availableW / trackBounds.width;
      const scaleY = availableH / trackBounds.height;
      const baseScale = Math.min(scaleX, scaleY);

      const fittedWidth = trackBounds.width * baseScale;
      const fittedHeight = trackBounds.height * baseScale;
      const offsetX = (width - fittedWidth) / 2;
      const offsetY = (height - fittedHeight) / 2;

      // Valores dinâmicos extraídos via ref para o frame atual
      const userZoom = userZoomRef.current;
      const userPan = userPanRef.current;
      const { showTags, showCorners, showDRSZones, showSectors } =
        viewOptionsRef.current;
      const currentDrivers = driversRef.current;
      const hoveredDriver = hoveredDriverRef.current;
      const selectedDriverId = selectedDriverIdRef.current;

      const transform: ViewTransform = {
        scale: baseScale,
        offsetX,
        offsetY,
        userScale: userZoom,
        panX: userPan.x,
        panY: userPan.y,
      };

      const points = trackData.points;
      const circuitLen =
        trackData.length_m || points[points.length - 1]?.distance_m || 4309;

      // -------------------------------------------------------------
      // 1. DESENHO DO ASFALTO E CONTORNO DA PISTA
      // -------------------------------------------------------------
      const screenPoints = points.map((p) =>
        worldToCanvas(p.x, p.y, width, height, transform),
      );

      // Traçado - Faixa Base de Asfalto (Larga)
      ctx.beginPath();
      screenPoints.forEach((pt, i) => {
        if (i === 0) ctx.moveTo(pt.x, pt.y);
        else ctx.lineTo(pt.x, pt.y);
      });
      ctx.closePath();

      // Sombra externa
      ctx.strokeStyle = "rgba(0, 0, 0, 0.6)";
      ctx.lineWidth = 26 * userZoom;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.stroke();

      // Superfície de asfalto
      ctx.strokeStyle = "#171d27";
      ctx.lineWidth = 20 * userZoom;
      ctx.stroke();

      // Bordas da pista (zebras sutis / guia branca)
      ctx.strokeStyle = "#334155";
      ctx.lineWidth = 2 * userZoom;
      ctx.stroke();

      // -------------------------------------------------------------
      // 2. SETORES DA PISTA (S1, S2, S3)
      // -------------------------------------------------------------
      if (showSectors && trackData.zones) {
        const sectorZones = trackData.zones.filter((z) => z.type === "sector");
        sectorZones.forEach((sz) => {
          const sNum = sz.props?.number || 1;
          const sectorColor =
            sNum === 1
              ? "rgba(168, 85, 247, 0.45)" // Roxo
              : sNum === 2
                ? "rgba(59, 130, 246, 0.45)" // Azul
                : "rgba(245, 158, 11, 0.45)"; // Âmbar

          ctx.beginPath();
          let started = false;
          for (const p of points) {
            if (p.distance_m >= sz.start_m && p.distance_m <= sz.end_m) {
              const sp = worldToCanvas(p.x, p.y, width, height, transform);
              if (!started) {
                ctx.moveTo(sp.x, sp.y);
                started = true;
              } else {
                ctx.lineTo(sp.x, sp.y);
              }
            }
          }
          if (started) {
            ctx.strokeStyle = sectorColor;
            ctx.lineWidth = 14 * userZoom;
            ctx.stroke();
          }

          // Marcador do início do setor
          const sectorStartPt = getPointAtDistance(
            sz.start_m,
            points,
            circuitLen,
          );
          const sSp = worldToCanvas(
            sectorStartPt.x,
            sectorStartPt.y,
            width,
            height,
            transform,
          );

          ctx.save();
          ctx.fillStyle =
            sNum === 1 ? "#C084FC" : sNum === 2 ? "#60A5FA" : "#FBBF24";
          ctx.beginPath();
          ctx.arc(sSp.x, sSp.y, 4 * userZoom, 0, Math.PI * 2);
          ctx.fill();

          ctx.font = `bold ${Math.max(9, 10 * userZoom)}px monospace`;
          ctx.fillStyle = "#E2E8F0";
          ctx.fillText(`S${sNum}`, sSp.x + 8 * userZoom, sSp.y + 3 * userZoom);
          ctx.restore();
        });
      }

      // -------------------------------------------------------------
      // 3. ZONAS DE DRS (ATIVAS / DETECÇÃO)
      // -------------------------------------------------------------
      if (showDRSZones && trackData.zones) {
        const drsZones = trackData.zones.filter(
          (z) => z.type === "drs_activation",
        );
        drsZones.forEach((dz) => {
          ctx.save();
          ctx.beginPath();
          let started = false;
          for (const p of points) {
            if (p.distance_m >= dz.start_m && p.distance_m <= dz.end_m) {
              const sp = worldToCanvas(p.x, p.y, width, height, transform);
              if (!started) {
                ctx.moveTo(sp.x, sp.y);
                started = true;
              } else {
                ctx.lineTo(sp.x, sp.y);
              }
            }
          }

          if (started) {
            ctx.shadowColor = "#10B981";
            ctx.shadowBlur = 12;
            ctx.strokeStyle = "#10B981";
            ctx.lineWidth = 6 * userZoom;
            ctx.stroke();
          }
          ctx.restore();

          // Placa indicativa de DRS
          const drsStartPt = getPointAtDistance(dz.start_m, points, circuitLen);
          const drsSp = worldToCanvas(
            drsStartPt.x,
            drsStartPt.y,
            width,
            height,
            transform,
          );
          ctx.save();
          ctx.font = `bold ${Math.max(8, 9 * userZoom)}px sans-serif`;
          ctx.fillStyle = "#10B981";
          ctx.fillText("DRS", drsSp.x - 10 * userZoom, drsSp.y - 10 * userZoom);
          ctx.restore();
        });
      }

      // -------------------------------------------------------------
      // 4. LINHA DE CHEGADA / LARGADA (distance = 0)
      // -------------------------------------------------------------
      const finishPt = getPointAtDistance(0, points, circuitLen);
      const finishScreen = worldToCanvas(
        finishPt.x,
        finishPt.y,
        width,
        height,
        transform,
      );

      // Traço perpendicular quadriculado / branco
      const normalAngle = finishPt.angle + Math.PI / 2;
      const barHalf = 13 * userZoom;
      const barX1 = finishScreen.x + Math.cos(normalAngle) * barHalf;
      const barY1 = finishScreen.y - Math.sin(normalAngle) * barHalf;
      const barX2 = finishScreen.x - Math.cos(normalAngle) * barHalf;
      const barY2 = finishScreen.y + Math.sin(normalAngle) * barHalf;

      ctx.save();
      ctx.beginPath();
      ctx.moveTo(barX1, barY1);
      ctx.lineTo(barX2, barY2);
      ctx.strokeStyle = "#FFFFFF";
      ctx.lineWidth = 4 * userZoom;
      ctx.stroke();

      // Ícone ou texto da linha de largada
      ctx.font = `bold ${Math.max(9, 10 * userZoom)}px sans-serif`;
      ctx.fillStyle = "#FFFFFF";
      ctx.fillText(
        "🏁",
        finishScreen.x + 8 * userZoom,
        finishScreen.y - 6 * userZoom,
      );
      ctx.restore();

      // -------------------------------------------------------------
      // 5. CURVAS E NOMES ANOTADOS (Contrato D4)
      // -------------------------------------------------------------
      if (showCorners && trackData.zones) {
        const corners = trackData.zones.filter((z) => z.type === "corner");
        corners.forEach((c) => {
          const midDist = (c.start_m + c.end_m) / 2;
          const cornerPt = getPointAtDistance(midDist, points, circuitLen);
          const cp = worldToCanvas(
            cornerPt.x,
            cornerPt.y,
            width,
            height,
            transform,
          );

          // Posição ligeiramente deslocada para fora da pista
          const offsetDist = 18 * userZoom;
          const textX =
            cp.x + Math.cos(cornerPt.angle + Math.PI / 2) * offsetDist;
          const textY =
            cp.y - Math.sin(cornerPt.angle + Math.PI / 2) * offsetDist;

          ctx.save();
          // Badge da curva
          ctx.fillStyle = "rgba(15, 23, 42, 0.85)";
          ctx.strokeStyle = "rgba(71, 85, 105, 0.6)";
          ctx.lineWidth = 1;
          const badgeText = `T${c.props?.number ?? ""}`;
          ctx.font = `bold ${Math.max(8, 9 * userZoom)}px monospace`;
          const textWidth = ctx.measureText(badgeText).width;

          ctx.beginPath();
          ctx.roundRect(
            textX - textWidth / 2 - 4,
            textY - 6,
            textWidth + 8,
            13,
            3,
          );
          ctx.fill();
          ctx.stroke();

          ctx.fillStyle = "#CBD5E1";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(badgeText, textX, textY + 1);

          // Se tiver zoom alto ou hover, exibe o nome (ex: "S do Senna")
          if (userZoom > 1.4 && c.props?.name) {
            ctx.font = "8px sans-serif";
            ctx.fillStyle = "#94A3B8";
            ctx.fillText(c.props.name, textX, textY + 11);
          }
          ctx.restore();
        });
      }

      // -------------------------------------------------------------
      // 6. CARROS E PILOTOS (Interpolação suave a 60 FPS)
      // -------------------------------------------------------------
      const currentAnimDistances = animDistancesRef.current;
      const sortedDrivers = [...currentDrivers].sort(
        (a, b) => b.position - a.position,
      ); // P1 desenhado por último para ficar por cima

      // Atualiza distâncias interpoladas
      currentDrivers.forEach((d) => {
        const targetD = d.distance_m || 0;
        const currentD = currentAnimDistances[d.driver_id] ?? targetD;

        // Trata a volta completa (cruzou de circuitLen para 0)
        let diff = targetD - currentD;
        if (diff < -circuitLen / 2) {
          diff += circuitLen;
        } else if (diff > circuitLen / 2) {
          diff -= circuitLen;
        }

        // Suavização exponencial rápida (lerp adaptativo)
        const lerpFactor = Math.min(1.0, deltaTime * 8.0);
        let nextD = currentD + diff * lerpFactor;
        if (nextD < 0) nextD += circuitLen;
        if (nextD >= circuitLen) nextD -= circuitLen;

        currentAnimDistances[d.driver_id] = nextD;
      });

      // Renderiza cada piloto
      sortedDrivers.forEach((driver) => {
        if (driver.is_retired) return; // Pilotos abandonados não circulam

        const dDist =
          currentAnimDistances[driver.driver_id] ?? driver.distance_m;
        const pt = getPointAtDistance(dDist, points, circuitLen);
        const basePos = worldToCanvas(pt.x, pt.y, width, height, transform);

        // Deslocamento leve para carros próximos evitarem sobreposição total
        const isHovered = hoveredDriver?.driver_id === driver.driver_id;
        const isSelected = selectedDriverId === driver.driver_id;
        const isLeader = driver.position === 1;

        const carRadius = (isLeader || isSelected ? 8 : 6.5) * userZoom;

        ctx.save();

        // 1. Halo / Anel de Efeito
        if (driver.drs_active) {
          // Pulso de DRS Verde Neon
          ctx.beginPath();
          ctx.arc(
            basePos.x,
            basePos.y,
            carRadius + 4 * userZoom,
            0,
            Math.PI * 2,
          );
          ctx.strokeStyle = "rgba(16, 185, 129, 0.85)";
          ctx.lineWidth = 2 * userZoom;
          ctx.shadowColor = "#10B981";
          ctx.shadowBlur = 8;
          ctx.stroke();
        }

        if (isLeader) {
          // Coroa dourada / Anel do Líder
          ctx.beginPath();
          ctx.arc(
            basePos.x,
            basePos.y,
            carRadius + 3 * userZoom,
            0,
            Math.PI * 2,
          );
          ctx.strokeStyle = "#F59E0B";
          ctx.lineWidth = 2.5 * userZoom;
          ctx.shadowColor = "#F59E0B";
          ctx.shadowBlur = 10;
          ctx.stroke();
        } else if (isSelected) {
          // Selecionado pelo usuário
          ctx.beginPath();
          ctx.arc(
            basePos.x,
            basePos.y,
            carRadius + 4 * userZoom,
            0,
            Math.PI * 2,
          );
          ctx.strokeStyle = "#FFFFFF";
          ctx.lineWidth = 2.5 * userZoom;
          ctx.shadowColor = "#FFFFFF";
          ctx.shadowBlur = 10;
          ctx.stroke();
        }

        // 2. Círculo do Carro (Cor da Equipe)
        ctx.beginPath();
        ctx.arc(basePos.x, basePos.y, carRadius, 0, Math.PI * 2);
        ctx.fillStyle = driver.teamColor || "#3B82F6";
        ctx.fill();

        // Borda do círculo
        ctx.strokeStyle = isLeader
          ? "#FCD34D"
          : isSelected
            ? "#FFFFFF"
            : "#0F172A";
        ctx.lineWidth = 1.8 * userZoom;
        ctx.stroke();

        // 3. Número da Posição dentro da bolinha
        ctx.font = `bold ${Math.max(7, 8 * userZoom)}px monospace`;
        ctx.fillStyle = "#FFFFFF";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(String(driver.position), basePos.x, basePos.y + 0.5);

        // 4. Etiqueta com Código FIA do Piloto (ex: VER, NOR, LEC)
        if (showTags || isHovered || isSelected || isLeader) {
          const tagOffset = (carRadius + 7) * userZoom;
          const tagX = basePos.x + tagOffset;
          const tagY = basePos.y - tagOffset;

          const tagText = `${driver.driver_id}`;
          ctx.font = `bold ${Math.max(8, 9 * userZoom)}px monospace`;
          const badgeW = ctx.measureText(tagText).width + 8;
          const badgeH = 14 * userZoom;

          // Fundo da etiqueta
          ctx.fillStyle = isSelected
            ? "rgba(15, 23, 42, 0.95)"
            : isLeader
              ? "rgba(245, 158, 11, 0.9)"
              : "rgba(15, 23, 42, 0.85)";
          ctx.strokeStyle = driver.teamColor || "#475569";
          ctx.lineWidth = 1;

          ctx.beginPath();
          ctx.roundRect(tagX - 2, tagY - badgeH / 2, badgeW, badgeH, 3);
          ctx.fill();
          ctx.stroke();

          // Texto FIA
          ctx.fillStyle = isLeader ? "#000000" : "#F8FAFC";
          ctx.textAlign = "left";
          ctx.textBaseline = "middle";
          ctx.fillText(tagText, tagX + 2, tagY);
        }

        ctx.restore();
      });

      ctx.restore();
      animationFrameIdRef.current = requestAnimationFrame(render);
    };

    animationFrameIdRef.current = requestAnimationFrame(render);

    return () => {
      isRunning = false;
      if (animationFrameIdRef.current) {
        cancelAnimationFrame(animationFrameIdRef.current);
      }
    };
  }, [trackData, trackBounds, worldToCanvas, getPointAtDistance]);

  // Wheel listener nativo com { passive: false } para suportar zoom sem warning no console e sem rolar a página
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;
      setUserZoom((prev) => Math.max(0.6, Math.min(4.5, prev * zoomFactor)));
    };

    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      canvas.removeEventListener("wheel", onWheel);
    };
  }, []);

  // Detector de Hover sobre pilotos
  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas || !trackData) return;

    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    if (isPanning) {
      setUserPan((prev) => ({
        x: prev.x + (e.clientX - startPan.x),
        y: prev.y + (e.clientY - startPan.y),
      }));
      setStartPan({ x: e.clientX, y: e.clientY });
      return;
    }

    setMousePos({ x: e.clientX, y: e.clientY });

    // Calcula se o mouse está sobre algum piloto
    const width = rect.width;
    const height = rect.height;

    const padding = 60;
    const availableW = Math.max(10, width - padding * 2);
    const availableH = Math.max(10, height - padding * 2);
    const baseScale = Math.min(
      availableW / trackBounds.width,
      availableH / trackBounds.height,
    );

    const currentZoom = userZoomRef.current;
    const currentPan = userPanRef.current;

    const transform: ViewTransform = {
      scale: baseScale,
      offsetX: (width - trackBounds.width * baseScale) / 2,
      offsetY: (height - trackBounds.height * baseScale) / 2,
      userScale: currentZoom,
      panX: currentPan.x,
      panY: currentPan.y,
    };

    const circuitLen = trackData.length_m || 4309;
    let foundDriver: EnrichedDriverState | null = null;

    for (const d of driversRef.current) {
      if (d.is_retired) continue;
      const dDist = animDistancesRef.current[d.driver_id] ?? d.distance_m;
      const pt = getPointAtDistance(dDist, trackData.points, circuitLen);
      const screenPos = worldToCanvas(pt.x, pt.y, width, height, transform);

      const dist = Math.hypot(mouseX - screenPos.x, mouseY - screenPos.y);
      if (dist <= 16 * currentZoom) {
        foundDriver = d;
        break;
      }
    }

    setHoveredDriver(foundDriver);
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (e.button === 0) {
      // Se clicou em um piloto, seleciona-o
      if (hoveredDriver) {
        onSelectDriver?.(
          selectedDriverId === hoveredDriver.driver_id
            ? null
            : hoveredDriver.driver_id,
        );
      } else {
        // Inicia arrastar (pan)
        setIsPanning(true);
        setStartPan({ x: e.clientX, y: e.clientY });
      }
    }
  };

  const handleMouseUp = () => {
    setIsPanning(false);
  };

  const resetView = () => {
    setUserZoom(1.0);
    setUserPan({ x: 0, y: 0 });
  };

  const minHeightClass = className.includes("min-h-") ? "" : "min-h-[380px]";

  return (
    <div
      ref={containerRef}
      className={`relative w-full h-full ${minHeightClass} bg-[#0c1017] rounded-xl border border-f1-border overflow-hidden shadow-2xl flex flex-col ${className}`}
    >
      {/* Barra de Título Superior do Circuito */}
      <div className="absolute top-3 left-3 z-20 flex items-center gap-2">
        <div className="bg-f1-dark/80 backdrop-blur-md border border-f1-border/80 px-3 py-1.5 rounded-lg shadow-lg flex items-center gap-2.5">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
          <div>
            <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-white">
              {circuitName}
            </h3>
            <p className="text-[10px] font-mono text-f1-muted">
              {trackData
                ? `${trackData.length_m}m • Canvas 2D Live Tracker`
                : "Carregando..."}
            </p>
          </div>
        </div>

        {/* Badge de Status da Pista */}
        {trackStatus !== "GREEN" && (
          <div className="bg-amber-500/20 border border-amber-500/60 px-2.5 py-1 rounded-md text-[11px] font-mono font-bold text-amber-300 animate-pulse flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5" />
            <span>{trackStatus}</span>
          </div>
        )}
      </div>

      {/* Controles do Canvas (Zoom e Camadas) */}
      <div className="absolute top-3 right-3 z-20 flex items-center gap-1.5 bg-f1-dark/80 backdrop-blur-md border border-f1-border/80 p-1 rounded-lg shadow-lg">
        {/* Toggle Tags */}
        <button
          type="button"
          onClick={() => setShowTags(!showTags)}
          title="Alternar Códigos dos Pilotos"
          className={`p-1.5 rounded text-xs font-mono transition-colors flex items-center gap-1 ${
            showTags
              ? "bg-f1-card text-white border border-f1-border"
              : "text-f1-muted hover:text-white"
          }`}
        >
          <Tag className="w-3.5 h-3.5" />
          <span className="hidden sm:inline text-[10px]">Pilotos</span>
        </button>

        {/* Toggle Curvas */}
        <button
          type="button"
          onClick={() => setShowCorners(!showCorners)}
          title="Alternar Curvas e Trechos"
          className={`p-1.5 rounded text-xs font-mono transition-colors flex items-center gap-1 ${
            showCorners
              ? "bg-f1-card text-white border border-f1-border"
              : "text-f1-muted hover:text-white"
          }`}
        >
          <Flag className="w-3.5 h-3.5" />
          <span className="hidden sm:inline text-[10px]">Curvas</span>
        </button>

        {/* Toggle DRS */}
        <button
          type="button"
          onClick={() => setShowDRSZones(!showDRSZones)}
          title="Alternar Zonas de DRS"
          className={`p-1.5 rounded text-xs font-mono transition-colors flex items-center gap-1 ${
            showDRSZones
              ? "bg-emerald-950/60 text-emerald-300 border border-emerald-500/50"
              : "text-f1-muted hover:text-white"
          }`}
        >
          <Zap className="w-3.5 h-3.5" />
          <span className="hidden sm:inline text-[10px]">DRS</span>
        </button>

        {/* Toggle Setores */}
        <button
          type="button"
          onClick={() => setShowSectors(!showSectors)}
          title="Alternar Setores S1/S2/S3"
          className={`p-1.5 rounded text-xs font-mono transition-colors flex items-center gap-1 ${
            showSectors
              ? "bg-f1-card text-white border border-f1-border"
              : "text-f1-muted hover:text-white"
          }`}
        >
          <Layers className="w-3.5 h-3.5" />
          <span className="hidden sm:inline text-[10px]">Setores</span>
        </button>

        <div className="w-[1px] h-4 bg-f1-border/80 my-auto mx-0.5"></div>

        {/* Zoom In */}
        <button
          type="button"
          onClick={() => setUserZoom((z) => Math.min(4.5, z * 1.25))}
          title="Aumentar Zoom"
          className="p-1.5 rounded text-f1-muted hover:text-white hover:bg-f1-card transition-colors"
        >
          <ZoomIn className="w-3.5 h-3.5" />
        </button>

        {/* Zoom Out */}
        <button
          type="button"
          onClick={() => setUserZoom((z) => Math.max(0.6, z * 0.8))}
          title="Diminuir Zoom"
          className="p-1.5 rounded text-f1-muted hover:text-white hover:bg-f1-card transition-colors"
        >
          <ZoomOut className="w-3.5 h-3.5" />
        </button>

        {/* Reset */}
        <button
          type="button"
          onClick={resetView}
          title="Resetar Enquadramento"
          className="p-1.5 rounded text-f1-muted hover:text-white hover:bg-f1-card transition-colors"
        >
          <RotateCcw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Elemento Canvas Real */}
      <div className="flex-1 min-h-0 w-full relative overflow-hidden cursor-grab active:cursor-grabbing">
        {loading && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-f1-dark/80 backdrop-blur-sm gap-2 font-mono text-xs text-slate-300">
            <div className="w-6 h-6 border-2 border-f1-red border-t-transparent rounded-full animate-spin"></div>
            <span>Renderizando geometria da pista...</span>
          </div>
        )}

        {error && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-f1-dark/90 gap-2 font-mono text-xs text-rose-300">
            <span>{error}</span>
            <button
              onClick={() => window.location.reload()}
              className="px-3 py-1 bg-f1-card hover:bg-f1-border text-white rounded border border-f1-border"
            >
              Recarregar
            </button>
          </div>
        )}

        <canvas
          ref={canvasRef}
          onMouseMove={handleMouseMove}
          onMouseDown={handleMouseDown}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          className="absolute inset-0 w-full h-full block"
        />

        {/* Tooltip de Telemetria F1 ao passar o mouse sobre um carro */}
        {hoveredDriver && mousePos && (
          <div
            className="fixed z-50 pointer-events-none transform -translate-x-1/2 -translate-y-full mb-3"
            style={{ left: mousePos.x, top: mousePos.y - 12 }}
          >
            <div className="bg-slate-900/95 backdrop-blur-md border border-slate-700/80 rounded-lg p-2.5 shadow-2xl text-xs font-mono text-white min-w-[210px]">
              <div className="flex items-center justify-between pb-1.5 border-b border-slate-800">
                <div className="flex items-center gap-2">
                  <div
                    className="w-2.5 h-2.5 rounded-full"
                    style={{ backgroundColor: hoveredDriver.teamColor }}
                  />
                  <span className="font-bold text-sm tracking-wide">
                    {hoveredDriver.driver_id}
                  </span>
                  <span className="text-slate-400 text-[11px] truncate max-w-[100px]">
                    {hoveredDriver.name}
                  </span>
                </div>
                <span className="font-bold text-amber-400">
                  P{hoveredDriver.position}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-x-3 gap-y-1 mt-2 text-[11px]">
                <div className="text-slate-400">Equipe:</div>
                <div className="font-semibold truncate">
                  {hoveredDriver.team}
                </div>

                <div className="text-slate-400">Gap Líder:</div>
                <div className="font-semibold text-right">
                  {formatGap(hoveredDriver.gap_to_leader)}
                </div>

                <div className="text-slate-400">Última Volta:</div>
                <div className="font-semibold text-right">
                  {formatLapTime(hoveredDriver.last_lap_time)}
                </div>

                <div className="text-slate-400">Pneu:</div>
                <div className="font-semibold flex items-center justify-end gap-1">
                  <span
                    className="px-1 py-0.2 rounded text-[10px]"
                    style={{
                      backgroundColor:
                        TYRE_INFO[hoveredDriver.tyre_compound]?.color + "22",
                      color: TYRE_INFO[hoveredDriver.tyre_compound]?.color,
                    }}
                  >
                    {hoveredDriver.tyre_compound[0]}
                  </span>
                  <span className="text-[10px] text-slate-400">
                    ({hoveredDriver.tyre_age}v)
                  </span>
                </div>

                <div className="text-slate-400">Combustível:</div>
                <div className="font-semibold text-right">
                  {hoveredDriver.fuel_load_kg.toFixed(1)} kg
                </div>

                {hoveredDriver.drs_active && (
                  <div className="col-span-2 mt-1 text-center bg-emerald-950/70 text-emerald-300 border border-emerald-500/40 rounded py-0.5 font-bold text-[10px]">
                    DRS ATIVO
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Barra Inferior com Legenda e Controles de Piloto Selecionado */}
      <div className="shrink-0 bg-f1-dark/90 border-t border-f1-border/60 px-4 py-2 flex flex-wrap items-center justify-between text-xs font-mono text-f1-muted gap-2">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-400 ring-2 ring-amber-400/30"></span>
            <span className="text-[11px] text-slate-300">Líder (P1)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 ring-2 ring-emerald-400/30"></span>
            <span className="text-[11px] text-slate-300">DRS Ativo</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-purple-500/50"></span>
            <span className="text-[11px] text-slate-300">S1</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-blue-500/50"></span>
            <span className="text-[11px] text-slate-300">S2</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-amber-500/50"></span>
            <span className="text-[11px] text-slate-300">S3</span>
          </div>
        </div>

        {selectedDriverId ? (
          <div className="flex items-center gap-2 bg-f1-card px-2.5 py-1 rounded border border-f1-border">
            <span className="text-white font-bold">
              Foco: {selectedDriverId}
            </span>
            <button
              onClick={() => onSelectDriver?.(null)}
              className="text-f1-muted hover:text-white"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        ) : (
          <div className="text-[11px] text-slate-400 hidden sm:block">
            Clique em um piloto na pista ou na tabela para fixar telemetria
          </div>
        )}
      </div>
    </div>
  );
};
