import json
from pathlib import Path
from typing import Dict, List

from config import DATA_DIR, DOCS_DIR

ONTOLOGY_EXTENSIONS = {".ttl", ".owl", ".rdf", ".nt", ".n3", ".trig"}
SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".pdf", ".docx", ".html", ".xml", ".yaml", ".yml"}


class DocumentRepository:
    """Gerencia o acesso e leitura de arquivos da pasta de documentos para a Sessão 2."""

    def __init__(self, docs_dir: Path = DOCS_DIR, fallback_dir: Path = DATA_DIR):
        self.root_dir = docs_dir if (docs_dir.exists() and any(docs_dir.rglob("*"))) else fallback_dir
        self._cache: Dict[str, str] = {}

    def _get_available_files(self) -> List[Path]:
        if not self.root_dir.exists():
            return []
        files = []
        for path in sorted(self.root_dir.rglob("*")):
            if not path.is_file():
                continue
            ext = path.suffix.lower()
            if ext in ONTOLOGY_EXTENSIONS:
                continue
            if ext in SUPPORTED_EXTENSIONS or not ext:
                files.append(path)
        return files

    def _extract_text(self, file_path: Path) -> str:
        rel_key = file_path.relative_to(self.root_dir).as_posix()
        if rel_key in self._cache:
            return self._cache[rel_key]

        ext = file_path.suffix.lower()
        text = ""
        try:
            if ext == ".pdf":
                from pypdf import PdfReader

                reader = PdfReader(str(file_path))
                pages = [page.extract_text() or "" for page in reader.pages]
                text = "\n\n".join(pages)
            elif ext == ".docx":
                from docx import Document

                doc = Document(str(file_path))
                text = "\n".join(p.text for p in doc.paragraphs if p.text)
            else:
                text = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            text = f"[Erro ao ler arquivo {rel_key}: {exc}]"

        self._cache[rel_key] = text
        return text

    def listar_documentos(self) -> str:
        files = self._get_available_files()
        if not files:
            return (
                f"Nenhum documento encontrado na pasta '{self.root_dir}'. "
                "Verifique se os arquivos foram adicionados em data/ ou data/docs/."
            )
        lines = [f"Documentos disponíveis ({len(files)} arquivos):"]
        for f in files:
            rel = f.relative_to(self.root_dir).as_posix()
            size_kb = f.stat().st_size / 1024
            lines.append(f"- {rel} ({size_kb:.1f} KB)")
        return "\n".join(lines)

    def ler_documento(
        self,
        caminho_arquivo: str,
        inicio_caractere: int = 0,
        limite_caracteres: int = 12000,
    ) -> str:
        files = self._get_available_files()
        target_norm = caminho_arquivo.strip().replace("\\", "/").lstrip("/")

        matched = None
        for f in files:
            rel = f.relative_to(self.root_dir).as_posix()
            if rel.lower() == target_norm.lower() or f.name.lower() == target_norm.lower():
                matched = f
                break

        if matched is None:
            return (
                f"Arquivo '{caminho_arquivo}' não encontrado. "
                "Use 'listar_documentos' para ver os nomes exatos dos arquivos."
            )

        content = self._extract_text(matched)
        total_len = len(content)
        inicio = max(0, int(inicio_caractere))
        limite = max(500, min(int(limite_caracteres), 30000))
        trecho = content[inicio : inicio + limite]

        rel = matched.relative_to(self.root_dir).as_posix()
        header = f"=== Arquivo: {rel} (caracteres {inicio} a {min(inicio + limite, total_len)} de {total_len}) ===\n"
        if inicio + limite < total_len:
            footer = f"\n...[Conteúdo truncado. Use inicio_caractere={inicio + limite} para ler o restante]..."
        else:
            footer = "\n=== Fim do arquivo ==="
        return header + trecho + footer

    def buscar_nos_documentos(self, termo: str, max_resultados: int = 10) -> str:
        termo_clean = termo.strip()
        if not termo_clean:
            return "Informe um termo não vazio para busca."

        files = self._get_available_files()
        if not files:
            return "Nenhum documento disponível para busca."

        termo_lower = termo_clean.lower()
        resultados = []

        for f in files:
            rel = f.relative_to(self.root_dir).as_posix()
            content = self._extract_text(f)
            content_lower = content.lower()

            start_idx = 0
            while len(resultados) < max_resultados:
                pos = content_lower.find(termo_lower, start_idx)
                if pos == -1:
                    break
                snippet_start = max(0, pos - 150)
                snippet_end = min(len(content), pos + len(termo_clean) + 250)
                snippet = content[snippet_start:snippet_end].replace("\n", " ")
                resultados.append(f"[{rel} @ char {pos}]: ...{snippet}...")
                start_idx = pos + len(termo_clean) + 100

            if len(resultados) >= max_resultados:
                break

        if not resultados:
            return f"Nenhuma ocorrência encontrada para o termo '{termo_clean}'."

        return (
            f"Ocorrências encontradas para '{termo_clean}' ({len(resultados)} trechos):\n"
            + "\n".join(resultados)
        )


DOCS_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "listar_documentos",
            "description": "Lista todos os arquivos e documentos disponíveis na pasta de dados sobre o Capstone do Insper.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_nos_documentos",
            "description": "Busca um termo ou palavra-chave em todos os documentos da pasta e retorna trechos relevantes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "termo": {
                        "type": "string",
                        "description": "Palavra-chave ou expressão a ser buscada nos documentos.",
                    },
                    "max_resultados": {
                        "type": "integer",
                        "description": "Número máximo de trechos retornados (padrão: 10).",
                        "default": 10,
                    },
                },
                "required": ["termo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ler_documento",
            "description": "Lê o conteúdo de texto de um documento específico da pasta.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caminho_arquivo": {
                        "type": "string",
                        "description": "Nome ou caminho relativo do arquivo retornado por listar_documentos.",
                    },
                    "inicio_caractere": {
                        "type": "integer",
                        "description": "Índice do caractere inicial para leitura paginada (padrão: 0).",
                        "default": 0,
                    },
                    "limite_caracteres": {
                        "type": "integer",
                        "description": "Quantidade máxima de caracteres a ler (padrão: 12000).",
                        "default": 12000,
                    },
                },
                "required": ["caminho_arquivo"],
            },
        },
    },
]


def execute_doc_tool(repo: DocumentRepository, name: str, arguments_json: str) -> str:
    try:
        args = json.loads(arguments_json) if arguments_json else {}
    except json.JSONDecodeError:
        args = {}

    if name == "listar_documentos":
        return repo.listar_documentos()
    if name == "buscar_nos_documentos":
        return repo.buscar_nos_documentos(
            termo=str(args.get("termo", "")),
            max_resultados=int(args.get("max_resultados", 10)),
        )
    if name == "ler_documento":
        return repo.ler_documento(
            caminho_arquivo=str(args.get("caminho_arquivo", "")),
            inicio_caractere=int(args.get("inicio_caractere", 0)),
            limite_caracteres=int(args.get("limite_caracteres", 12000)),
        )
    return f"Ferramenta desconhecida: {name}"

