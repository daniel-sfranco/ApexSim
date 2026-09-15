// Placeholder do serviço `web` do docker-compose, sem dependências.
// Existe só para o ambiente inteiro subir com `make up` na semana 1.
// O scaffold real (Next.js + TypeScript + Tailwind) é entregável do Anderson —
// ele substitui este diretório por cima, mantendo `npm run dev` como comando.

const http = require("http");

const PORT = 3000;

const PAGINA = `<!doctype html>
<meta charset="utf-8">
<title>ApexSim — web (placeholder)</title>
<body style="font-family: system-ui; max-width: 40rem; margin: 4rem auto; line-height: 1.6">
  <h1>ApexSim — serviço web</h1>
  <p>Placeholder da semana 1. O scaffold Next.js entra na ficha M0 do Anderson.</p>
  <p>API: <a href="http://localhost:8000/health">localhost:8000/health</a></p>
</body>`;

http
  .createServer((_req, res) => {
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    res.end(PAGINA);
  })
  .listen(PORT, "0.0.0.0", () => {
    console.log(`web placeholder em http://localhost:${PORT}`);
  });
