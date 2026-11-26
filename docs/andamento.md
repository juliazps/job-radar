# Andamento do fork (juliazps/job-radar)

Notas de trabalho para retomar de onde parou. Última atualização: 26/11/2026.

## Regra do fork

- Este é um fork de `liliamkezia-star/job-radar`. **Nenhuma mudança daqui vai
  para o projeto original**: nada de PR para lá e nada de push para o
  `upstream`. Tudo vai só para `juliazps/job-radar`.
- Puxar atualizações da Liliam (botão **Sync fork** no GitHub) é permitido,
  porque o caminho é só de lá para cá.

## Feito

1. **Teste da busca (perfil Brasil, ciclo completo, banco de cópia, sem
   Telegram):** 7.885 vagas lidas → 1.549 passaram no filtro → 23 inéditas,
   todas do LinkedIn (20 iriam na hora, 3 para o digest). Único erro: timeout
   da Catho num termo. Duração de ~22 min. Rodou antes das fontes novas.
2. **Fontes novas no perfil Brasil** (commit `28b7b91`), as duas em
   `FREQUENCIA_ALTA`:
   - **Remotar** (`scrapers/remotar.py`), por API: 23,2% aprovadas, 103
     inéditas na medição.
   - **InfoJobs** (`scrapers/infojobs.py`), por HTML: busca geral + listagem
     home office. Paginação só funciona com `Page`, P maiúsculo.
   - Avaliados e descartados: vagas.com.br (0 aprovadas), BNE (403),
     Jobconvo (sem busca pública), ProgramaThor, Coodesh. Motivos registrados
     em `core/perfis.py`.
   - Critério de permanência: 3 inéditas aprovadas em 14 dias, senão a fonte
     sai.
3. **Correção da deduplicação com empresa genérica** (commit `8e681c7`):
   vagas "Confidencial" com o mesmo título em cidades diferentes não se
   anulam mais. A fórmula única está em `core/job.py`
   (`calcular_chave_secundaria`).
4. As duas mudanças estão na `main` do fork. São 757 testes, todos passando.

## Pendente (para a Julia fazer no GitHub)

- Ativar os workflows na aba **Actions** do fork (vem desligado em fork).
- Cadastrar os secrets `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` (bot próprio,
  via @BotFather).

## Próximos passos combinados

- **Novo canal de alerta.** Recomendação: **Discord com bot**, que mantém o
  feedback 👍/👎 lendo as reações via API, sem servidor, então funciona no
  Actions. WhatsApp via CallMeBot só serve como aviso extra (não tem
  feedback). A API oficial do WhatsApp é paga e burocrática. Ideia de
  arquitetura: uma interface `Notificador` (`enviar_vaga`, `enviar_digest`,
  `ler_feedback`), com o Telegram como uma implementação e o canal ligado
  quando o token estiver presente.
- Opcional: rodar um ciclo de teste já com Remotar e InfoJobs para medir o
  ganho real.
- Acompanhar o critério de permanência das fontes novas (até ~10/12).

## Como testar localmente sem notificar ninguém

```bash
JOBRADAR_DB_PATH=/tmp/teste.db python main.py --perfil brasil --once
```

Use uma cópia de `data/jobs.db` no `/tmp/teste.db` para a deduplicação valer
como em produção. Sem `TELEGRAM_BOT_TOKEN`, as vagas aparecem no log como
"Falha ao notificar" e não são marcadas como vistas.
