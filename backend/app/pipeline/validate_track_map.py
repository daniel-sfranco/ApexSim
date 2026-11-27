"""Script de validação lógica do Contrato D4 (`track_map`).

Garante que os arquivos JSON anotados em `track_maps/{circuito}.json`
respeitam rigorosamente todas as restrições da Seção 4 do `docs/track-map-schema.md`.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any

from app.config import TRACK_MAPS_DIR

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("track_validator")


class ValidationError(Exception):
    """Erro de violação de contrato do mapa de pistas."""

    pass


def validate_track_dict(data: dict[str, Any], filename: str = "") -> list[str]:
    """Valida a estrutura do dicionário de um mapa de pistas contra as regras D4.

    Retorna uma lista de strings com os erros encontrados (vazia se válido).
    """
    errors: list[str] = []
    prefix = f"[{filename}] " if filename else ""

    # 1. Metadados Gerais
    circuit_id = data.get("circuit_id")
    if not circuit_id or not isinstance(circuit_id, str):
        errors.append(f"{prefix}circuit_id obrigatório e deve ser string não vazia.")

    length_m = data.get("length_m")
    if length_m is None or not isinstance(length_m, (int, float)) or length_m <= 0:
        errors.append(f"{prefix}length_m deve ser um número maior que zero.")
        return errors  # sem length_m válido não é possível checar limites espaciais

    points = data.get("points")
    if not points or not isinstance(points, list) or len(points) < 200:
        found_pts = len(points) if isinstance(points, list) else 0
        errors.append(
            f"{prefix}points deve conter pelo menos 200 pontos ({found_pts} encontrados)."
        )
    else:
        # Fechamento do último ponto dentro de margem razoável (< 1%)
        last_dist = points[-1].get("distance_m", 0)
        if abs(length_m - last_dist) / length_m > 0.015:
            errors.append(
                f"{prefix}Último ponto (distance_m={last_dist}m) difere >1% de {length_m}m."
            )

    zones = data.get("zones")
    if not isinstance(zones, list):
        errors.append(f"{prefix}zones deve ser uma lista.")
        return errors

    # 2. Limites Espaciais e Ordem de Cada Zona
    point_types = {"drs_detection", "pit_entry", "pit_exit"}
    interval_types = {"sector", "corner", "braking_zone", "straight", "drs_activation", "pit_lane"}

    valid_severities = {"baixa", "media", "alta"}
    valid_runoffs = {"brita", "asfalto", "muro"}

    for idx, z in enumerate(zones):
        z_type = z.get("type")
        start_m = z.get("start_m")
        end_m = z.get("end_m")
        props = z.get("props", {})

        if not z_type or not isinstance(z_type, str):
            errors.append(f"{prefix}Zona #{idx + 1}: type obrigatório e deve ser string.")
            continue

        if start_m is None or not isinstance(start_m, (int, float)):
            errors.append(f"{prefix}Zona #{idx + 1} ({z_type}): start_m numérico obrigatório.")
            continue

        if end_m is None or not isinstance(end_m, (int, float)):
            errors.append(f"{prefix}Zona #{idx + 1} ({z_type}): end_m numérico obrigatório.")
            continue

        # Nenhuma zona pode ultrapassar length_m ou ser menor que 0
        if start_m < 0 or start_m > length_m:
            errors.append(
                f"{prefix}Zona #{idx + 1} ({z_type}): start_m ({start_m}m) fora [0, {length_m}m]."
            )
        if end_m < 0 or end_m > length_m:
            errors.append(
                f"{prefix}Zona #{idx + 1} ({z_type}): end_m ({end_m}m) fora [0, {length_m}m]."
            )
        if start_m > end_m:
            errors.append(
                f"{prefix}Zona #{idx + 1} ({z_type}): start_m ({start_m}m) > end_m ({end_m}m)."
            )

        # 3. Zonas Pontuais vs Intervalos
        if z_type in point_types and start_m != end_m:
            errors.append(
                f"{prefix}Zona #{idx + 1} pontual ({z_type}): start ({start_m}) != end ({end_m})."
            )

        if z_type in interval_types and start_m == end_m:
            errors.append(
                f"{prefix}Zona #{idx + 1} de intervalo ({z_type}): requer start_m < end_m."
            )

        # 4. Propriedades Específicas
        if z_type == "braking_zone":
            sev = props.get("severity")
            runoff = props.get("runoff")
            if sev not in valid_severities:
                errors.append(f"{prefix}Frenagem #{idx + 1}: severity inválida ('{sev}').")
            if runoff not in valid_runoffs:
                errors.append(f"{prefix}Frenagem #{idx + 1}: runoff inválida ('{runoff}').")

        elif z_type == "pit_lane":
            speed = props.get("speed_limit_kmh")
            time_loss = props.get("time_loss_s")
            if not isinstance(speed, (int, float)) or speed <= 0:
                errors.append(
                    f"{prefix}pit_lane #{idx + 1}: speed_limit_kmh deve ser número positivo."
                )
            if not isinstance(time_loss, (int, float)) or time_loss <= 0:
                errors.append(f"{prefix}pit_lane #{idx + 1}: time_loss_s deve ser número positivo.")

    # 5. Setores: exatamente 3 setores cobrindo [0, length_m] contíguos
    sectors = [z for z in zones if z.get("type") == "sector"]
    sectors.sort(key=lambda s: s.get("start_m", 0))

    if len(sectors) != 3:
        errors.append(f"{prefix}Devem existir exatamente 3 setores (encontrados: {len(sectors)}).")
    else:
        if sectors[0].get("start_m") != 0:
            errors.append(
                f"{prefix}Setor 1 deve começar em 0m (começa em {sectors[0].get('start_m')}m)."
            )
        if sectors[0].get("end_m") != sectors[1].get("start_m"):
            s1_end = sectors[0].get("end_m")
            s2_start = sectors[1].get("start_m")
            errors.append(
                f"{prefix}Setor 1 termina em {s1_end}m, mas Setor 2 começa em {s2_start}m."
            )
        if sectors[1].get("end_m") != sectors[2].get("start_m"):
            s2_end = sectors[1].get("end_m")
            s3_start = sectors[2].get("start_m")
            errors.append(
                f"{prefix}Setor 2 termina em {s2_end}m, mas Setor 3 começa em {s3_start}m."
            )
        if sectors[2].get("end_m") != length_m:
            errors.append(f"{prefix}Setor 3 deve terminar em {length_m}m.")

    # 6. Presença Mínima Obrigatória de Elementos do Contrato
    has_drs_det = any(z.get("type") == "drs_detection" for z in zones)
    has_drs_act = any(z.get("type") == "drs_activation" for z in zones)
    has_pit_entry = any(z.get("type") == "pit_entry" for z in zones)
    has_pit_lane = any(z.get("type") == "pit_lane" for z in zones)
    has_pit_exit = any(z.get("type") == "pit_exit" for z in zones)
    has_braking = any(z.get("type") == "braking_zone" for z in zones)

    if not (has_drs_det and has_drs_act):
        errors.append(f"{prefix}Circuito deve conter zonas de DRS (detecção e ativação).")
    if not (has_pit_entry and has_pit_lane and has_pit_exit):
        errors.append(
            f"{prefix}Circuito deve conter boxes completos (pit_entry, pit_lane e pit_exit)."
        )
    if not has_braking:
        errors.append(
            f"{prefix}Circuito deve conter pelo menos uma zona de frenagem (braking_zone)."
        )

    return errors


def validate_file(path: Path) -> list[str]:
    """Lê e valida um arquivo JSON de mapa de pista."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"[{path.name}] Erro ao ler JSON: {e}"]
    return validate_track_dict(data, filename=path.name)


def main() -> int:
    """Função CLI que percorre os mapas de pista e emite relatório."""
    json_files = sorted(TRACK_MAPS_DIR.glob("*.json"))
    if not json_files:
        logger.error(f"Nenhum arquivo de mapa encontrado em {TRACK_MAPS_DIR}")
        return 1

    total_errors = 0
    logger.info("=" * 65)
    logger.info("  ApexSim — Validador Lógico do Contrato D4 (track_maps/)")
    logger.info("=" * 65)

    for f in json_files:
        errs = validate_file(f)
        if errs:
            total_errors += len(errs)
            logger.error(f"\n❌ {f.name} — {len(errs)} erro(s) encontrado(s):")
            for e in errs:
                logger.error(f"   • {e}")
        else:
            data = json.loads(f.read_text(encoding="utf-8"))
            z_count = len(data.get("zones", []))
            l_m = data.get("length_m", 0)
            logger.info(f"✅ {f.name:<18} [PASS]  ({z_count:2d} zonas, L={l_m}m)")

    logger.info("=" * 65)
    if total_errors == 0:
        logger.info("🎉 Todos os mapas de pista são 100% válidos conforme o Contrato D4!")
        return 0
    else:
        logger.error(f"⚠️ Total de erros de validação: {total_errors}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
