// Servidor WebSocket Mock do ApexSim (Contrato D2)
// Sincronizado com frontend/scripts/mock-server.js

const path = require('path');
const mockScript = path.resolve(__dirname, '../../frontend/scripts/mock-server.cjs');

try {
  require(mockScript);
} catch (err) {
  console.error('Erro ao inicializar mock server compartilhado:', err);
}