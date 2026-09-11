const WebSocket = require('ws');

const server = new WebSocket.Server({ port: 8080 });

server.on('connection', (socket) => {
  console.log('Novo cliente conectado!');

  socket.on('message', (message) => {
    console.log(`Mensagem recebida: ${message}`);
    // Envia a mensagem de volta para o cliente (eco)
    socket.send(`Servidor recebeu: ${message}`);
  });

  socket.on('close', () => {
    console.log('Cliente desconectado.');
  });
});

console.log('Servidor WebSocket rodando na porta ws://localhost:8080');