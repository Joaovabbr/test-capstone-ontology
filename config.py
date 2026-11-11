import os
from pathlib import Path
from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# Configuração da API do OpenRouter
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# Diretórios e arquivos de entrada/saída
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DOCS_DIR = Path(os.getenv("DOCS_DIR", DATA_DIR / "docs"))
ONTOLOGY_FILE = Path(os.getenv("ONTOLOGY_FILE", DATA_DIR / "capstone_insper.ttl"))
QUESTIONS_FILE = Path(os.getenv("QUESTIONS_FILE", BASE_DIR / "perguntas.txt"))

RESULTS_DIR = Path(os.getenv("RESULTS_DIR", BASE_DIR / "results"))
ANSWERS_DIR = Path(os.getenv("ANSWERS_DIR", RESULTS_DIR / "respostas"))
METRICS_DIR = Path(os.getenv("METRICS_DIR", RESULTS_DIR / "metricas"))

# Modelos a serem testados: chave amigável (usada no nome do arquivo) -> slug no OpenRouter
MODELS = {
    "gemini-3.8-flash": os.getenv("MODEL_GEMINI", "google/gemini-3.8-flash"),
    "claude-opus-5": os.getenv("MODEL_CLAUDE", "anthropic/claude-opus-5"),
    "gpt-5.6-luna": os.getenv("MODEL_GPT", "openai/gpt-5.6-luna"),
}

# Limite máximo de iterações de chamadas de ferramentas (tool calls) por pergunta
MAX_TOOL_ITERATIONS = int(os.getenv("MAX_TOOL_ITERATIONS", "10"))

# Prompts de sistema para cada uma das 3 sessões
SYSTEM_PROMPTS = {
    "sem_documentos": (
        "Você é um assistente prestativo respondendo perguntas sobre o projeto "
        "Capstone do Insper. Responda de forma direta, clara e objetiva em português, "
        "utilizando apenas o seu conhecimento geral."
    ),
    "documentos": (
        "Você é um assistente prestativo respondendo perguntas sobre o projeto "
        "Capstone do Insper. Você tem acesso a ferramentas para listar, buscar e ler "
        "documentos locais na pasta de dados do projeto. Antes de responder, consulte "
        "os documentos disponíveis usando as ferramentas fornecidas para embasar sua "
        "resposta com precisão. Responda de forma direta, clara e objetiva em português."
    ),
    "ontologia": (
        "Você é um assistente especialista respondendo perguntas sobre o projeto "
        "Capstone do Insper com acesso a uma Ontologia (grafo de conhecimento em formato "
        "RDF/Turtle). Você possui ferramentas para inspecionar o esquema da ontologia "
        "(classes, propriedades e prefixos), buscar entidades/termos no grafo, explorar "
        "triplas de uma entidade e executar consultas SPARQL. Sempre consulte o grafo da "
        "ontologia utilizando as ferramentas antes de responder para garantir máxima "
        "fidelidade conceitual e estrutural. Responda de forma direta, clara e objetiva em português."
    ),
}
