# Benchmark de Ontologia do Capstone Insper via OpenRouter

Este repositório realiza o teste automatizado de modelos de linguagem (LLMs) via **OpenRouter API** respondendo perguntas sobre o tema **Capstone do Insper** em **3 sessões distintas** para cada modelo:

1. **Sessão 1 (`sem_documentos`)**: O modelo responde apenas com seu conhecimento padrão, sem acesso a arquivos ou ferramentas externas.
2. **Sessão 2 (`documentos`)**: O modelo recebe ferramentas (`listar_documentos`, `buscar_nos_documentos`, `ler_documento`) para consultar uma pasta com diversos arquivos (`.txt`, `.md`, `.pdf`, `.docx`, `.csv`, etc.).
3. **Sessão 3 (`ontologia`)**: O modelo recebe ferramentas de consulta em grafo (`obter_esquema_ontologia`, `executar_consulta_sparql`, `buscar_termo_no_grafo`, `explorar_entidade`) conectadas à ontologia Turtle (`.ttl`) do Capstone do Insper.

## Modelos Configurados

- **Gemini 3.8 Flash** (`gemini-3.8-flash` -> `google/gemini-3.8-flash`)
- **Claude Opus 5** (`claude-opus-5` -> `anthropic/claude-opus-5`)
- **GPT 5.6-luna** (`gpt-5.6-luna` -> `openai/gpt-5.6-luna`)

> Caso os identificadores (slugs) dos modelos no OpenRouter sejam diferentes na sua conta, basta ajustá-los no arquivo `.env` (`MODEL_GEMINI`, `MODEL_CLAUDE`, `MODEL_GPT`) ou em `config.py`.

## Estrutura de Pastas e Dados

A pasta `/data` e o arquivo `.env` já estão ignorados no `.gitignore`. Organize seus arquivos da seguinte forma:

```text
.
├── data/
│   ├── ontologia.ttl       # Sua ontologia em formato Turtle (.ttl)
│   └── docs/               # Pasta com os documentos para a Sessão 2 (.pdf, .docx, .txt, .md, etc.)
├── perguntas.txt           # Uma pergunta por linha (separadas por \n)
├── .env                    # Sua chave OPENROUTER_API_KEY
├── config.py
├── tools_docs.py
├── tools_ontology.py
└── main.py
```

*(Observação: se qualquer arquivo `.ttl` for colocado dentro de `data/`, ele será detectado automaticamente pela ferramenta de ontologia, e os demais arquivos em `data/docs/` ou `data/` serão disponibilizados apenas na Sessão 2).*

## Instalação e Configuração

1. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

2. Crie o arquivo `.env` a partir do exemplo:
   ```bash
   cp .env.example .env
   ```
   Edite o `.env` e insira sua chave do OpenRouter:
   ```env
   OPENROUTER_API_KEY=sk-or-v1-...
   ```

3. Edite o arquivo `perguntas.txt` colocando uma pergunta por linha (separadas por `\n`).

## Como Executar

Para rodar o teste completo (todos os 3 modelos nas 3 sessões):

```bash
python main.py
```

Opções úteis de linha de comando:
- Rodar apenas um modelo específico:
  ```bash
  python main.py --modelos gemini-3.8-flash
  ```
- Rodar apenas uma sessão específica:
  ```bash
  python main.py --sessoes ontologia
  ```
- Manter histórico de mensagens entre as perguntas da mesma sessão:
  ```bash
  python main.py --manter-historico
  ```

## Arquivos de Saída e Métricas

Ao final da execução, são gerados:
- `respostas_{modelo}.txt`: Arquivo consolidado do modelo contendo as 3 sessões, o tempo total, o gasto de tokens (`prompt_tokens`, `completion_tokens`, `total_tokens`) e as respostas numeradas (`1- primeira resposta\n2- segunda resposta`).
- `respostas_{modelo}_{sessao}.txt`: Arquivo individual por sessão no formato estrito `1- primeira resposta\n2- segunda resposta` acompanhado do resumo de tokens e tempo.
- `metricas_teste.json` e `metricas_teste.csv`: Relatórios completos com o tempo gasto e consumo de tokens por pergunta, por sessão e por modelo.

