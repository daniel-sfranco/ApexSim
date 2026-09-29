// Teste de validação do Mock WebSocket Server e Contrato D2
const { WebSocket } = require("ws");
const { spawn } = require("child_process");
const assert = require("assert");

console.log("▶ Iniciando teste de validação do Mock Server e Contrato D2...");

const TEST_PORT = 8089;
const server = spawn("node", ["scripts/mock-server.js"], {
  env: { ...process.env, MOCK_PORT: TEST_PORT },
});

server.stderr.on("data", (data) => {
  console.error("Mock Server Stderr:", data.toString());
});

let testPassed = false;

server.stdout.on("data", (data) => {
  const text = data.toString();
  if (text.includes("ApexSim Mock WebSocket Server ativo")) {
    runClientTest();
  }
});

function runClientTest() {
  const ws = new WebSocket(`ws://localhost:${TEST_PORT}`);

  let step = 0;
  let initialLap = 0;

  ws.on("open", () => {
    console.log("✓ Cliente conectado ao Mock Server na porta", TEST_PORT);
  });

  ws.on("message", (raw) => {
    const msg = JSON.parse(raw.toString());

    if (msg.type === "lap_update") {
      console.log(`✓ Mensagem lap_update recebida (Volta ${msg.current_lap}/${msg.total_laps}, Status ${msg.track_status})`);

      // 1. Validar campos de envelope
      assert.strictEqual(msg.type, "lap_update", "Tipo deve ser lap_update");
      assert(typeof msg.race_id === "string", "race_id deve ser string");
      assert(typeof msg.current_lap === "number", "current_lap deve ser number");
      assert(typeof msg.total_laps === "number", "total_laps deve ser number");
      assert(["GREEN", "YELLOW", "SAFETY_CAR", "RED"].includes(msg.track_status), "track_status inválido");
      assert(Array.isArray(msg.drivers), "drivers deve ser array");
      assert.strictEqual(msg.drivers.length, 20, "Devem existir exatamente 20 pilotos");

      // 2. Validar integridade dos pilotos
      const leader = msg.drivers.find((d) => d.position === 1);
      assert(leader, "Deve existir um piloto na posição 1 (líder)");
      assert.strictEqual(leader.gap_to_leader, 0.0, "Gap do líder deve ser 0.0");
      assert.strictEqual(leader.gap_to_ahead, null, "Gap to ahead do líder deve ser null");

      msg.drivers.forEach((driver) => {
        assert(typeof driver.driver_id === "string", "driver_id inválido");
        assert(typeof driver.name === "string", "driver name inválido");
        assert(typeof driver.position === "number", "driver position inválido");
        assert(typeof driver.gap_to_leader === "number", "gap_to_leader inválido");
        assert(["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"].includes(driver.tyre_compound), "tyre_compound inválido");
        assert(typeof driver.tyre_age === "number", "tyre_age inválido");
        assert(typeof driver.fuel_load_kg === "number", "fuel_load_kg inválido");
        assert(["NONE", "ENTERING", "IN_PIT", "EXITING"].includes(driver.pit_status), "pit_status inválido");
      });

      step++;

      if (step === 1) {
        initialLap = msg.current_lap;
        // Testar set_speed para acelerar simulação no teste
        console.log("✓ Enviando comando set_speed (10x)...");
        ws.send(JSON.stringify({ action: "set_speed", speed_multiplier: 10 }));
      } else if (step === 2) {
        assert(msg.current_lap > initialLap, "A volta deve ter avançado");
        // Testar pause
        console.log("✓ Enviando comando pause...");
        ws.send(JSON.stringify({ action: "pause" }));

        setTimeout(() => {
          // Testar resume
          console.log("✓ Enviando comando resume...");
          ws.send(JSON.stringify({ action: "resume" }));
        }, 500);
      } else if (step >= 4) {
        console.log("✓ Todas as validações do contrato D2 passaram com sucesso!");
        testPassed = true;
        ws.close();
        server.kill();
        process.exit(0);
      }
    }
  });
}

setTimeout(() => {
  if (!testPassed) {
    console.error("❌ Teste falhou por timeout!");
    server.kill();
    process.exit(1);
  }
}, 8000);
