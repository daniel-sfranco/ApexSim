# 📝 Convenções de Commit — ApexSim

Para garantir a organização e rastreabilidade do nosso código, adotamos o padrão **Conventional Commits**. Todas as mensagens de commit devem seguir a estrutura abaixo:

<tipo>(<escopo>): <descrição curta em letras minúsculas>


## 1. Tipos de Commit
*   **feat:** Uma nova funcionalidade (ex: modelo de desgaste, nova tela do front).
*   **fix:** Correção de um bug (ex: gap calculado errado no motor, erro de renderização no mapa).
*   **docs:** Alterações apenas em arquivos de documentação (ex: esquemas de API, equações de física).
*   **style:** Mudanças estéticas que não afetam o comportamento do código (ex: formatação, lint, CSS).
*   **refactor:** Alteração de código que não corrige bugs nem adiciona novas funcionalidades (ex: renomeação de variáveis, quebra de funções longas).
*   **test:** Adição ou correção de testes unitários ou de integração.
*   **chore:** Tarefas de infraestrutura que não alteram código de produção (ex: Dockerfile, dependências do package.json, configuração de CI).

## 2. Nossos Escopos Recomendados
Para facilitar a leitura do histórico do repositório, tente associar o commit à sua respectiva trilha ou módulo utilizando um destes escopos:

*   `sim` (Motor de Simulação — Gabriel)
*   `physics` (Física & Eventos Estocásticos — Isaac)
*   `strategy` (Modelagem de Pista, Estratégia e IA — Daniel)
*   `front` (Frontend & Interface — Anderson)
*   `data` (Banco de dados e Ingestão — Octávio)
*   `infra` (Docker, CI/CD, Makefiles — Geral/Octávio)

## 3. Exemplos Práticos
*   `feat(physics): implementar formula de degradacao de pneus macios`
*   `fix(sim): corrigir ordenacao de posicoes na timing tower apos ultrapassagem`
*   `docs(strategy): adicionar schema inicial do track_map em markdown`
*   `test(front): adicionar teste unitario para animacao de troca de posicao`
*   `chore(infra): configurar workflows do github actions para lint automatico`
