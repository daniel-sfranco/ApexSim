// Mock WebSocket Server do ApexSim (Ficha Anderson M0 e M1)
// Emite mensagens `lap_update` e `event_update` segundo o Contrato D2.
// Suporta comandos de controle: play, pause, resume, set_speed, restart.

const { WebSocketServer, WebSocket } = require('ws');

const PORT = process.env.MOCK_PORT || process.env.PORT || 8080;

const DRIVER_POOL = [
  { driver_id: 'VER', name: 'Max Verstappen', team: 'Red Bull Racing', team_color: '#3671C6' },
  { driver_id: 'NOR', name: 'Lando Norris', team: 'McLaren', team_color: '#FF8000' },
  { driver_id: 'LEC', name: 'Charles Leclerc', team: 'Ferrari', team_color: '#E8002D' },
  { driver_id: 'PIA', name: 'Oscar Piastri', team: 'McLaren', team_color: '#FF8000' },
  { driver_id: 'SAI', name: 'Carlos Sainz', team: 'Ferrari', team_color: '#E8002D' },
  { driver_id: 'HAM', name: 'Lewis Hamilton', team: 'Mercedes', team_color: '#27F4D2' },
  { driver_id: 'RUS', name: 'George Russell', team: 'Mercedes', team_color: '#27F4D2' },
  { driver_id: 'PER', name: 'Sergio Pérez', team: 'Red Bull Racing', team_color: '#3671C6' },
  { driver_id: 'ALO', name: 'Fernando Alonso', team: 'Aston Martin', team_color: '#229971' },
  { driver_id: 'STR', name: 'Lance Stroll', team: 'Aston Martin', team_color: '#229971' },
  { driver_id: 'TSU', name: 'Yuki Tsunoda', team: 'RB', team_color: '#6692FF' },
  { driver_id: 'LAW', name: 'Liam Lawson', team: 'RB', team_color: '#6692FF' },
  { driver_id: 'GAS', name: 'Pierre Gasly', team: 'Alpine', team_color: '#0093CC' },
  { driver_id: 'OCO', name: 'Esteban Ocon', team: 'Alpine', team_color: '#0093CC' },
  { driver_id: 'ALB', name: 'Alexander Albon', team: 'Williams', team_color: '#64C4FF' },
  { driver_id: 'COL', name: 'Franco Colapinto', team: 'Williams', team_color: '#64C4FF' },
  { driver_id: 'HUL', name: 'Nico Hülkenberg', team: 'Haas', team_color: '#B6BABD' },
  { driver_id: 'MAG', name: 'Kevin Magnussen', team: 'Haas', team_color: '#B6BABD' },
  { driver_id: 'BOT', name: 'Valtteri Bottas', team: 'Kick Sauber', team_color: '#52E252' },
  { driver_id: 'ZHO', name: 'Zhou Guanyu', team: 'Kick Sauber', team_color: '#52E252' },
];

class MockRaceSimulator {
  constructor(totalLaps = 53, circuitId = 'interlagos') {
    this.raceId = 'mock-' + Math.random().toString(36).substring(2, 9);
    this.totalLaps = totalLaps;
    this.circuitId = circuitId;
    this.currentLap = 0;
    this.isPaused = false;
    this.speedMultiplier = 1.0;
    this.trackStatus = 'GREEN';
    this.weather = 'DRY';
    this.trackTemp = 32.5;
    this.circuitLength = 4309;
    this.timer = null;
    this.scRemainingLaps = 0;

    this.drivers = DRIVER_POOL.map((driver, index) => ({
      driver_id: driver.driver_id,
      name: driver.name,
      team: driver.team,
      team_color: driver.team_color,
      position: index + 1,
      total_time: 0.0,
      gap_to_leader: index === 0 ? 0.0 : Number((index * 1.25).toFixed(3)),
      gap_to_ahead: index === 0 ? null : 1.25,
      last_lap_time: null,
      tyre_compound: index % 3 === 0 ? 'SOFT' : index % 3 === 1 ? 'MEDIUM' : 'HARD',
      tyre_age: 0,
      fuel_load_kg: 105.0,
      pit_status: 'NONE',
      pit_stops_made: 0,
      is_retired: false,
      drs_active: false,
      distance_m: Number(((DRIVER_POOL.length - index) * (4309 / DRIVER_POOL.length)).toFixed(1)),
    }));
  }

  start(broadcastCallback) {
    this.broadcast = broadcastCallback;
    this.scheduleNextTick();
  }

  scheduleNextTick() {
    if (this.timer) clearTimeout(this.timer);
    if (this.currentLap >= this.totalLaps) {
      console.log(`[MockServer] Corrida finalizada na volta ${this.totalLaps}!`);
      return;
    }

    const intervalMs = Math.max(200, Math.floor(2000 / this.speedMultiplier));
    this.timer = setTimeout(() => {
      if (!this.isPaused) {
        this.stepLap();
      }
      this.scheduleNextTick();
    }, intervalMs);
  }

  stepLap() {
    this.currentLap += 1;

    // Gerenciamento de Safety Car simulado
    if (this.scRemainingLaps > 0) {
      this.scRemainingLaps -= 1;
      if (this.scRemainingLaps === 0) {
        this.trackStatus = 'GREEN';
        if (this.broadcast) {
          this.broadcast({
            type: 'event_update',
            race_id: this.raceId,
            lap: this.currentLap,
            event_type: 'SAFETY_CAR_IN',
            involved_drivers: [],
            zone_id: null,
            description: 'Safety Car entrando nesta volta. Pista liberada para relargada.',
          });
        }
      }
    } else if (this.currentLap === 15 || this.currentLap === 34) {
      // Evento de bandeira amarela / SC para teste de UI
      this.trackStatus = 'SAFETY_CAR';
      this.scRemainingLaps = 2;
      const unluckyDriver = this.drivers[Math.min(18, Math.floor(Math.random() * 5 + 14))];
      if (this.broadcast) {
        this.broadcast({
          type: 'event_update',
          race_id: this.raceId,
          lap: this.currentLap,
          event_type: 'SAFETY_CAR_DEPLOYED',
          involved_drivers: [unluckyDriver.driver_id],
          zone_id: 's_do_senna_brake',
          description: `Incidente na pista com ${unluckyDriver.name}. Safety Car acionado.`,
        });
      }
    }

    // Variação climática sutil
    this.trackTemp = Number((this.trackTemp + (Math.random() * 0.4 - 0.2)).toFixed(1));

    // Simulação do tempo de volta de cada piloto
    this.drivers.forEach((driver) => {
      driver.tyre_age += 1;
      driver.fuel_load_kg = Number(Math.max(5.0, driver.fuel_load_kg - 1.6).toFixed(1));

      // Degradação de pneu
      const tyreFactor =
        driver.tyre_compound === 'SOFT' ? 0.08 :
        driver.tyre_compound === 'MEDIUM' ? 0.05 : 0.03;
      const tyrePenalty = driver.tyre_age * tyreFactor;

      // Tempo de volta base (~81-83s dependendo do status da pista)
      const baseLap = this.trackStatus === 'SAFETY_CAR' ? 115.0 : 81.5;
      const randomNoise = (Math.random() - 0.5) * 0.8;
      const fuelBonus = (105.0 - driver.fuel_load_kg) * 0.03; // mais leve = mais rapido
      const lapTime = Number((baseLap + tyrePenalty - fuelBonus + randomNoise).toFixed(3));

      driver.last_lap_time = lapTime;
      driver.total_time += lapTime;

      // Simulação de Pit Stop se o pneu estiver velho (> 16 voltas para soft, > 22 para medium)
      const shouldPit =
        (driver.tyre_compound === 'SOFT' && driver.tyre_age >= 16) ||
        (driver.tyre_compound === 'MEDIUM' && driver.tyre_age >= 23) ||
        (driver.tyre_compound === 'HARD' && driver.tyre_age >= 32);

      if (shouldPit && driver.pit_status === 'NONE') {
        driver.pit_status = 'IN_PIT';
        driver.pit_stops_made += 1;
        driver.total_time += 22.5; // perda de tempo no pit lane
        const nextCompound = driver.tyre_compound === 'SOFT' ? 'HARD' : 'MEDIUM';
        driver.tyre_compound = nextCompound;
        driver.tyre_age = 0;

        if (this.broadcast) {
          this.broadcast({
            type: 'event_update',
            race_id: this.raceId,
            lap: this.currentLap,
            event_type: 'PIT_STOP',
            involved_drivers: [driver.driver_id],
            zone_id: 'pit_lane',
            description: `${driver.name} (${driver.team}) realizou pit stop e colocou pneus ${nextCompound}.`,
          });
        }
      } else if (driver.pit_status === 'IN_PIT') {
        driver.pit_status = 'NONE';
      }

      // DRS status
      driver.drs_active = driver.position > 1 && driver.gap_to_ahead !== null && driver.gap_to_ahead < 1.0;
    });

    // Possibilidade de ultrapassagem estocástica entre carros próximos
    for (let i = 1; i < this.drivers.length; i++) {
      const behind = this.drivers[i];
      const ahead = this.drivers[i - 1];
      if (behind.gap_to_ahead !== null && behind.gap_to_ahead < 0.6 && Math.random() < 0.35) {
        // Ultrapassagem acontece!
        behind.total_time = ahead.total_time - 0.2;
        if (this.broadcast) {
          this.broadcast({
            type: 'event_update',
            race_id: this.raceId,
            lap: this.currentLap,
            event_type: 'OVERTAKE',
            involved_drivers: [behind.driver_id, ahead.driver_id],
            zone_id: 'drs_activation',
            description: `${behind.name} ultrapassou ${ahead.name} assumindo a posição ${ahead.position}!`,
          });
        }
      }
    }

    // Reordenar os pilotos pelo tempo total de corrida
    this.drivers.sort((a, b) => a.total_time - b.total_time);

    // Recalcular posições e gaps
    const leaderTime = this.drivers[0].total_time;
    this.drivers.forEach((driver, idx) => {
      driver.position = idx + 1;
      if (idx === 0) {
        driver.gap_to_leader = 0.0;
        driver.gap_to_ahead = null;
      } else {
        const aheadTime = this.drivers[idx - 1].total_time;
        driver.gap_to_leader = Number((driver.total_time - leaderTime).toFixed(3));
        driver.gap_to_ahead = Number((driver.total_time - aheadTime).toFixed(3));
      }
      driver.distance_m = Number((Math.random() * this.circuitLength).toFixed(1));
    });

    // Emitir mensagem lap_update segundo contrato D2
    const lapMessage = this.getLapUpdateEnvelope();
    if (this.broadcast) {
      this.broadcast(lapMessage);
    }
  }

  getLapUpdateEnvelope() {
    return {
      type: 'lap_update',
      race_id: this.raceId,
      current_lap: this.currentLap,
      total_laps: this.totalLaps,
      track_status: this.trackStatus,
      weather: this.weather,
      track_temp: this.trackTemp,
      drivers: this.drivers.map((d) => ({
        driver_id: d.driver_id,
        name: d.name,
        team: d.team,
        position: d.position,
        gap_to_leader: d.gap_to_leader,
        gap_to_ahead: d.gap_to_ahead,
        last_lap_time: d.last_lap_time,
        tyre_compound: d.tyre_compound,
        tyre_age: d.tyre_age,
        fuel_load_kg: d.fuel_load_kg,
        pit_status: d.pit_status,
        pit_stops_made: d.pit_stops_made,
        is_retired: d.is_retired,
        drs_active: d.drs_active,
        distance_m: d.distance_m,
      })),
    };
  }

  pause() {
    this.isPaused = true;
    console.log('[MockServer] Simulação pausada');
  }

  resume() {
    this.isPaused = false;
    console.log('[MockServer] Simulação retomada');
  }

  setSpeed(multiplier) {
    this.speedMultiplier = Math.max(0.25, Math.min(20.0, multiplier));
    console.log(`[MockServer] Velocidade ajustada para ${this.speedMultiplier}x`);
  }

  restart(totalLaps = 53, circuitId = 'interlagos') {
    if (this.timer) clearTimeout(this.timer);
    const newSim = new MockRaceSimulator(totalLaps, circuitId);
    Object.assign(this, newSim);
    console.log('[MockServer] Corrida reiniciada');
    this.scheduleNextTick();
  }
}

// Inicia servidor WebSocket
const wss = new WebSocketServer({ port: PORT });
const simulator = new MockRaceSimulator(53, 'interlagos');

function broadcast(data) {
  const jsonStr = JSON.stringify(data);
  wss.clients.forEach((client) => {
    if (client.readyState === WebSocket.OPEN) {
      client.send(jsonStr);
    }
  });
}

simulator.start(broadcast);

wss.on('connection', (ws, req) => {
  console.log(`[MockServer] Cliente conectado: ${req.url}`);

  // Envia imediatamente o estado da volta atual para não esperar o tick
  ws.send(JSON.stringify(simulator.getLapUpdateEnvelope()));

  ws.on('message', (message) => {
    try {
      const payload = JSON.parse(message.toString());
      console.log('[MockServer] Comando recebido:', payload);

      if (payload.action === 'pause') {
        simulator.pause();
      } else if (payload.action === 'resume' || payload.action === 'play') {
        simulator.resume();
      } else if (payload.action === 'set_speed' && typeof payload.speed_multiplier === 'number') {
        simulator.setSpeed(payload.speed_multiplier);
      } else if (payload.action === 'restart') {
        simulator.restart(payload.total_laps || 53, payload.circuit_id || 'interlagos');
        ws.send(JSON.stringify(simulator.getLapUpdateEnvelope()));
      }
    } catch (err) {
      console.error('[MockServer] Erro ao processar mensagem do cliente:', err);
    }
  });

  ws.on('close', () => {
    console.log('[MockServer] Cliente desconectado');
  });
});

console.log(`🏁 ApexSim Mock WebSocket Server ativo em ws://localhost:${PORT}`);
console.log('Emitindo mensagens "lap_update" a cada 2s (ajustável via set_speed)');
