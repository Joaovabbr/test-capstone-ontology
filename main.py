import argparse
import csv
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List

from openai import OpenAI

from config import (
    ANSWERS_DIR,
    DATA_DIR,
    DOCS_DIR,
    MAX_TOOL_ITERATIONS,
    METRICS_DIR,
    MODELS,
    ONTOLOGY_FILE,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    QUESTIONS_FILE,
    SYSTEM_PROMPTS,
)
from tools_docs import DOCS_TOOLS_SCHEMA, DocumentRepository, execute_doc_tool
from tools_ontology import ONTOLOGY_TOOLS_SCHEMA, OntologyGraphTool, execute_ontology_tool


@dataclass
class QuestionResult:
    numero: int
    pergunta: str
    resposta: str
    tempo_segundos: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    chamadas_ferramentas: int


@dataclass
class SessionMetrics:
    modelo_nome: str
    modelo_slug: str
    sessao: str
    tempo_total_segundos: float = 0.0
    prompt_tokens_total: int = 0
    completion_tokens_total: int = 0
    total_tokens: int = 0
    total_chamadas_ferramentas: int = 0
    respostas: List[QuestionResult] = field(default_factory=list)


SESSION_TYPES = [
    ("sem_documentos", "Sessão 1: Sem Documentos (Conhecimento Padrão)"),
    ("documentos", "Sessão 2: Acesso à Pasta de Documentos"),
    ("ontologia", "Sessão 3: Acesso à Ontologia (Grafo RDF/Turtle)"),
]


def load_questions(questions_file: Path) -> List[str]:
    if not questions_file.exists():
        raise FileNotFoundError(
            f"Arquivo de perguntas '{questions_file}' não encontrado. "
            "Crie o arquivo 'perguntas.txt' com uma pergunta por linha."
        )
    raw_lines = questions_file.read_text(encoding="utf-8").splitlines()
    questions = [line.strip() for line in raw_lines if line.strip()]
    if not questions:
        raise ValueError(f"O arquivo '{questions_file}' não contém perguntas válidas.")
    return questions


def format_single_line_answer(text: str) -> str:
    """Compacta quebras de linha internas para manter o padrão '1- resposta\\n2- resposta'."""
    cleaned = " ".join(line.strip() for line in text.strip().splitlines() if line.strip())
    return cleaned


def run_question_in_session(
    client: OpenAI,
    model_slug: str,
    session_type: str,
    question: str,
    session_history: List[Dict[str, Any]],
    doc_repo: DocumentRepository,
    ontology_tool: OntologyGraphTool,
    keep_history: bool = False,
) -> QuestionResult:
    """Executa uma pergunta na sessão correspondente, resolvendo chamadas de ferramentas se houver."""
    if session_type == "documentos":
        tools = DOCS_TOOLS_SCHEMA
    elif session_type == "ontologia":
        tools = ONTOLOGY_TOOLS_SCHEMA
    else:
        tools = None

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPTS[session_type]}
    ]
    if keep_history and session_history:
        messages.extend(session_history)

    messages.append({"role": "user", "content": question})

    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    tool_calls_count = 0
    final_answer = ""

    start_time = time.perf_counter()

    try:
        for _ in range(MAX_TOOL_ITERATIONS):
            kwargs: Dict[str, Any] = {
                "model": model_slug,
                "messages": messages,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            response = client.chat.completions.create(**kwargs)

            if response.usage:
                p_tok = getattr(response.usage, "prompt_tokens", 0) or 0
                c_tok = getattr(response.usage, "completion_tokens", 0) or 0
                t_tok = getattr(response.usage, "total_tokens", 0) or (p_tok + c_tok)
                prompt_tokens += p_tok
                completion_tokens += c_tok
                total_tokens += t_tok

            choice = response.choices[0]
            msg = choice.message

            if msg.tool_calls:
                assistant_msg: Dict[str, Any] = {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                }
                messages.append(assistant_msg)

                for tc in msg.tool_calls:
                    tool_calls_count += 1
                    fn_name = tc.function.name
                    fn_args = tc.function.arguments or "{}"

                    if session_type == "documentos":
                        tool_output = execute_doc_tool(doc_repo, fn_name, fn_args)
                    elif session_type == "ontologia":
                        tool_output = execute_ontology_tool(ontology_tool, fn_name, fn_args)
                    else:
                        tool_output = "Nenhuma ferramenta disponível nesta sessão."

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": fn_name,
                            "content": tool_output,
                        }
                    )
                continue

            final_answer = msg.content or ""
            break
        else:
            # Caso atinja o limite de tool calls, solicita resposta final sem ferramentas
            messages.append(
                {
                    "role": "user",
                    "content": "Com base nas informações coletadas até aqui, forneça sua resposta final para a pergunta.",
                }
            )
            response = client.chat.completions.create(model=model_slug, messages=messages)
            if response.usage:
                p_tok = getattr(response.usage, "prompt_tokens", 0) or 0
                c_tok = getattr(response.usage, "completion_tokens", 0) or 0
                t_tok = getattr(response.usage, "total_tokens", 0) or (p_tok + c_tok)
                prompt_tokens += p_tok
                completion_tokens += c_tok
                total_tokens += t_tok
            final_answer = response.choices[0].message.content or ""

    except Exception as exc:
        final_answer = f"[ERRO na chamada ao modelo '{model_slug}': {exc}]"

    elapsed = time.perf_counter() - start_time

    if keep_history:
        session_history.append({"role": "user", "content": question})
        session_history.append({"role": "assistant", "content": final_answer})

    return QuestionResult(
        numero=0,
        pergunta=question,
        resposta=final_answer,
        tempo_segundos=round(elapsed, 4),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        chamadas_ferramentas=tool_calls_count,
    )


def save_model_outputs(
    model_name: str,
    model_slug: str,
    sessions_metrics: List[SessionMetrics],
    answers_dir: Path,
    single_line: bool = True,
) -> Path:
    answers_dir.mkdir(parents=True, exist_ok=True)
    consolidated_file = answers_dir / f"respostas_{model_name}.txt"

    total_model_tokens = sum(s.total_tokens for s in sessions_metrics)
    total_model_time = sum(s.tempo_total_segundos for s in sessions_metrics)

    consolidated_lines: List[str] = [
        f"# Modelo: {model_name} ({model_slug})",
        f"# Tempo Total Geral: {total_model_time:.2f}s | Tokens Totais Gerais: {total_model_tokens}",
        "",
    ]

    for sess_metric in sessions_metrics:
        sess_label = dict(SESSION_TYPES).get(sess_metric.sessao, sess_metric.sessao)
        consolidated_lines.append(f"=== {sess_label} ===")
        consolidated_lines.append(
            f"Tempo total da sessão: {sess_metric.tempo_total_segundos:.2f}s | "
            f"Tokens totais da sessão: {sess_metric.total_tokens} "
            f"(Prompt: {sess_metric.prompt_tokens_total}, "
            f"Completion: {sess_metric.completion_tokens_total}) | "
            f"Chamadas de ferramentas: {sess_metric.total_chamadas_ferramentas}"
        )

        for q_res in sess_metric.respostas:
            ans_text = (
                format_single_line_answer(q_res.resposta)
                if single_line
                else q_res.resposta.strip()
            )
            line = f"{q_res.numero}- {ans_text}"
            consolidated_lines.append(line)

        consolidated_lines.append("")

    consolidated_file.write_text("\n".join(consolidated_lines), encoding="utf-8")
    return consolidated_file


def save_global_metrics(all_metrics: List[SessionMetrics], metrics_dir: Path) -> None:
    metrics_dir.mkdir(parents=True, exist_ok=True)

    # Salva JSON detalhado
    json_path = metrics_dir / "metricas_teste.json"
    json_data = [asdict(m) for m in all_metrics]
    json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Salva CSV consolidado por sessão
    csv_path = metrics_dir / "metricas_teste.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "modelo_nome",
                "modelo_slug",
                "sessao",
                "tempo_total_segundos",
                "prompt_tokens_total",
                "completion_tokens_total",
                "total_tokens",
                "total_chamadas_ferramentas",
            ]
        )
        for m in all_metrics:
            writer.writerow(
                [
                    m.modelo_nome,
                    m.modelo_slug,
                    m.sessao,
                    f"{m.tempo_total_segundos:.4f}",
                    m.prompt_tokens_total,
                    m.completion_tokens_total,
                    m.total_tokens,
                    m.total_chamadas_ferramentas,
                ]
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Executa o benchmark automatizado de LLMs (OpenRouter) em 3 sessões sobre o Capstone do Insper."
    )
    parser.add_argument(
        "--perguntas",
        type=Path,
        default=QUESTIONS_FILE,
        help="Caminho para o arquivo perguntas.txt (padrão: perguntas.txt).",
    )
    parser.add_argument(
        "--ontologia",
        type=Path,
        default=ONTOLOGY_FILE,
        help="Caminho para o arquivo .ttl da ontologia (padrão: data/capstone_insper.ttl).",
    )
    parser.add_argument(
        "--docs",
        type=Path,
        default=DOCS_DIR,
        help="Caminho para a pasta de documentos da Sessão 2 (padrão: data/docs ou data/).",
    )
    parser.add_argument(
        "--modelos",
        nargs="*",
        default=list(MODELS.keys()),
        choices=list(MODELS.keys()),
        help="Filtra quais modelos executar (padrão: todos os 3 modelos).",
    )
    parser.add_argument(
        "--sessoes",
        nargs="*",
        default=[s[0] for s in SESSION_TYPES],
        choices=[s[0] for s in SESSION_TYPES],
        help="Filtra quais sessões executar (padrão: sem_documentos, documentos, ontologia).",
    )
    parser.add_argument(
        "--manter-historico",
        action="store_true",
        help="Se ativado, mantém o histórico das perguntas anteriores dentro da mesma sessão.",
    )
    parser.add_argument(
        "--multilinha",
        action="store_true",
        help="Preserva quebras de linha dentro de cada resposta em vez de compactar em uma linha por número.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not OPENROUTER_API_KEY:
        print(
            "[ERRO] A variável OPENROUTER_API_KEY não foi definida no arquivo .env.",
            file=sys.stderr,
        )
        print(
            "Crie um arquivo .env (baseado no .env.example) contendo OPENROUTER_API_KEY=sua_chave.",
            file=sys.stderr,
        )
        sys.exit(1)

    questions = load_questions(args.perguntas)
    print(f"Carregadas {len(questions)} perguntas de '{args.perguntas}'.")

    doc_repo = DocumentRepository(docs_dir=args.docs, fallback_dir=DATA_DIR)
    ontology_tool = OntologyGraphTool(ontology_path=args.ontologia, data_dir=DATA_DIR)

    if ontology_tool.load_error:
        print(f"[AVISO Ontologia] {ontology_tool.load_error}")
    else:
        print(
            f"Ontologia carregada com sucesso: '{ontology_tool.ontology_path}' "
            f"({len(ontology_tool.graph)} triplas)."
        )

    client = OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
    )

    all_metrics: List[SessionMetrics] = []

    for model_name in args.modelos:
        model_slug = MODELS[model_name]
        print(f"\n============================================================")
        print(f"Iniciando testes para o modelo: {model_name} ({model_slug})")
        print(f"============================================================")

        model_sessions_metrics: List[SessionMetrics] = []

        for session_key, session_desc in SESSION_TYPES:
            if session_key not in args.sessoes:
                continue

            print(f"\n-> Executando {session_desc}...")
            sess_metric = SessionMetrics(
                modelo_nome=model_name,
                modelo_slug=model_slug,
                sessao=session_key,
            )
            session_history: List[Dict[str, Any]] = []

            for idx, question in enumerate(questions, start=1):
                print(f"   [{idx}/{len(questions)}] Pergunta: {question[:70]}...")
                q_result = run_question_in_session(
                    client=client,
                    model_slug=model_slug,
                    session_type=session_key,
                    question=question,
                    session_history=session_history,
                    doc_repo=doc_repo,
                    ontology_tool=ontology_tool,
                    keep_history=args.manter_historico,
                )
                q_result.numero = idx
                sess_metric.respostas.append(q_result)
                sess_metric.tempo_total_segundos += q_result.tempo_segundos
                sess_metric.prompt_tokens_total += q_result.prompt_tokens
                sess_metric.completion_tokens_total += q_result.completion_tokens
                sess_metric.total_tokens += q_result.total_tokens
                sess_metric.total_chamadas_ferramentas += q_result.chamadas_ferramentas

                print(
                    f"       Concluída em {q_result.tempo_segundos:.2f}s | "
                    f"Tokens: {q_result.total_tokens} | "
                    f"Tool calls: {q_result.chamadas_ferramentas}"
                )

            sess_metric.tempo_total_segundos = round(sess_metric.tempo_total_segundos, 4)
            model_sessions_metrics.append(sess_metric)
            all_metrics.append(sess_metric)

            print(
                f"   [Resumo {session_key}] Tempo total: {sess_metric.tempo_total_segundos:.2f}s | "
                f"Tokens totais: {sess_metric.total_tokens}"
            )

        out_file = save_model_outputs(
            model_name=model_name,
            model_slug=model_slug,
            sessions_metrics=model_sessions_metrics,
            answers_dir=ANSWERS_DIR,
            single_line=not args.multilinha,
        )
        print(f"\nRespostas do modelo '{model_name}' salvas em: {out_file}")

    save_global_metrics(all_metrics, METRICS_DIR)
    print("\n============================================================")
    print("Teste finalizado! Relatórios de métricas salvos em:")
    print(f" - {METRICS_DIR / 'metricas_teste.json'}")
    print(f" - {METRICS_DIR / 'metricas_teste.csv'}")
    print("============================================================")


if __name__ == "__main__":
    main()
