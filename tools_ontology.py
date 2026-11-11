import json
from pathlib import Path
from typing import Optional

from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL, URIRef

from config import DATA_DIR, ONTOLOGY_FILE


class OntologyGraphTool:
    """Carrega a ontologia Turtle (.ttl) e disponibiliza ferramentas de consulta em grafo e SPARQL."""

    def __init__(self, ontology_path: Path = ONTOLOGY_FILE, data_dir: Path = DATA_DIR):
        self.ontology_path = self._resolve_ontology_path(ontology_path, data_dir)
        self.graph = Graph()
        self.load_error: Optional[str] = None
        self._load_graph()

    @staticmethod
    def _resolve_ontology_path(ontology_path: Path, data_dir: Path) -> Path:
        if ontology_path.exists() and ontology_path.is_file():
            return ontology_path
        if data_dir.exists():
            ttl_files = sorted(data_dir.rglob("*.ttl"))
            if ttl_files:
                return ttl_files[0]
        return ontology_path

    def _load_graph(self) -> None:
        if not self.ontology_path.exists():
            self.load_error = (
                f"Arquivo de ontologia não encontrado em '{self.ontology_path}'. "
                "Coloque o arquivo .ttl na pasta 'data/' (ex.: data/ontologia.ttl)."
            )
            return
        try:
            self.graph.parse(str(self.ontology_path), format="turtle")
        except Exception as exc:
            self.load_error = f"Erro ao carregar a ontologia '{self.ontology_path}': {exc}"

    def _format_node(self, node) -> str:
        if isinstance(node, URIRef):
            try:
                return self.graph.namespace_manager.normalizeUri(node)
            except Exception:
                return str(node)
        if isinstance(node, Literal):
            return f'"{node}"'
        return str(node)

    def _local_name(self, uri: str) -> str:
        if "#" in uri:
            return uri.rsplit("#", 1)[-1]
        if "/" in uri.rstrip("/"):
            return uri.rstrip("/").rsplit("/", 1)[-1]
        return uri

    def obter_esquema_ontologia(self) -> str:
        if self.load_error:
            return self.load_error

        lines = [
            f"=== Esquema da Ontologia ({self.ontology_path.name}) ===",
            f"Total de triplas no grafo: {len(self.graph)}",
            "\n--- Prefixos (Namespaces) ---",
        ]
        for prefix, ns in sorted(self.graph.namespaces(), key=lambda x: x[0]):
            lines.append(f"PREFIX {prefix}: <{ns}>")

        # Classes declaradas ou usadas em rdf:type
        classes = set()
        for cls_type in (OWL.Class, RDFS.Class):
            for s in self.graph.subjects(RDF.type, cls_type):
                if isinstance(s, URIRef):
                    classes.add(s)
        for _, _, o in self.graph.triples((None, RDF.type, None)):
            if isinstance(o, URIRef) and not str(o).startswith((str(OWL), str(RDFS), str(RDF))):
                classes.add(o)

        lines.append(f"\n--- Classes ({len(classes)}) ---")
        for c in sorted(classes, key=lambda x: str(x)):
            labels = [str(lbl) for lbl in self.graph.objects(c, RDFS.label)]
            comments = [str(cmt) for cmt in self.graph.objects(c, RDFS.comment)]
            sub_of = [
                self._format_node(sup)
                for sup in self.graph.objects(c, RDFS.subClassOf)
                if isinstance(sup, URIRef)
            ]
            desc = self._format_node(c)
            if labels:
                desc += f" | label: {', '.join(labels)}"
            if sub_of:
                desc += f" | subClassOf: {', '.join(sub_of)}"
            if comments:
                desc += f" | comment: {comments[0][:140]}"
            lines.append(f"- {desc}")

        # Propriedades de Objeto, Dados e Predicados usados
        obj_props = set(self.graph.subjects(RDF.type, OWL.ObjectProperty))
        data_props = set(self.graph.subjects(RDF.type, OWL.DatatypeProperty))
        all_preds = {p for _, p, _ in self.graph if isinstance(p, URIRef)}

        lines.append(f"\n--- Object Properties ({len(obj_props)}) ---")
        for p in sorted(obj_props, key=lambda x: str(x)):
            domains = [self._format_node(d) for d in self.graph.objects(p, RDFS.domain)]
            ranges = [self._format_node(r) for r in self.graph.objects(p, RDFS.range)]
            labels = [str(lbl) for lbl in self.graph.objects(p, RDFS.label)]
            info = self._format_node(p)
            if labels:
                info += f" ({', '.join(labels)})"
            if domains or ranges:
                info += f" [{', '.join(domains) or '*'} -> {', '.join(ranges) or '*'}]"
            lines.append(f"- {info}")

        lines.append(f"\n--- Datatype Properties ({len(data_props)}) ---")
        for p in sorted(data_props, key=lambda x: str(x)):
            domains = [self._format_node(d) for d in self.graph.objects(p, RDFS.domain)]
            ranges = [self._format_node(r) for r in self.graph.objects(p, RDFS.range)]
            labels = [str(lbl) for lbl in self.graph.objects(p, RDFS.label)]
            info = self._format_node(p)
            if labels:
                info += f" ({', '.join(labels)})"
            if domains or ranges:
                info += f" [{', '.join(domains) or '*'} -> {', '.join(ranges) or '*'}]"
            lines.append(f"- {info}")

        other_preds = all_preds - obj_props - data_props
        lines.append(f"\n--- Outros Predicados Utilizados no Grafo ({len(other_preds)}) ---")
        for p in sorted(other_preds, key=lambda x: str(x))[:40]:
            lines.append(f"- {self._format_node(p)}")

        # Indivíduos / Instâncias
        individuals = []
        for s, _, o in self.graph.triples((None, RDF.type, None)):
            if isinstance(s, URIRef) and o in classes:
                individuals.append((s, o))

        if individuals:
            lines.append(f"\n--- Indivíduos/Instâncias ({len(individuals)} encontradas, exibindo até 50) ---")
            for s, o in individuals[:50]:
                labels = [str(lbl) for lbl in self.graph.objects(s, RDFS.label)]
                lbl_str = f" ({', '.join(labels)})" if labels else ""
                lines.append(f"- {self._format_node(s)}{lbl_str} [rdf:type {self._format_node(o)}]")

        return "\n".join(lines)

    def executar_consulta_sparql(self, query: str) -> str:
        if self.load_error:
            return self.load_error

        # Prepara declarações de PREFIX automaticamente se não estiverem na consulta
        prefix_lines = []
        query_upper = query.upper()
        for prefix, ns in self.graph.namespaces():
            decl = f"PREFIX {prefix}: <{ns}>"
            if f"PREFIX {prefix.upper()}:" not in query_upper:
                prefix_lines.append(decl)

        full_query = "\n".join(prefix_lines) + "\n" + query

        try:
            results = self.graph.query(full_query)
        except Exception as exc:
            return f"Erro ao executar consulta SPARQL: {exc}\nVerifique a sintaxe e os prefixos com 'obter_esquema_ontologia'."

        if results.type == "ASK":
            return f"Resultado ASK: {bool(results.askAnswer)}"

        if results.type in ("CONSTRUCT", "DESCRIBE") and results.graph is not None:
            triples = [
                f"{self._format_node(s)} {self._format_node(p)} {self._format_node(o)} ."
                for s, p, o in results.graph
            ]
            return f"Triplas retornadas ({len(triples)}):\n" + "\n".join(triples[:100])

        vars_list = [str(v) for v in (results.vars or [])]
        rows = []
        for row in results:
            row_dict = {}
            for idx, var_name in enumerate(vars_list):
                val = row[idx]
                row_dict[var_name] = self._format_node(val) if val is not None else "None"
            rows.append(row_dict)

        if not rows:
            return "A consulta SPARQL executou com sucesso, mas retornou 0 resultados."

        output_lines = [f"Resultados SPARQL ({len(rows)} linhas):"]
        for i, r in enumerate(rows[:100], start=1):
            cols = " | ".join(f"?{k} = {v}" for k, v in r.items())
            output_lines.append(f"{i}. {cols}")

        if len(rows) > 100:
            output_lines.append(f"... ({len(rows) - 100} linhas adicionais omitidas)")

        return "\n".join(output_lines)

    def buscar_termo_no_grafo(self, termo: str, limite: int = 40) -> str:
        if self.load_error:
            return self.load_error

        termo_clean = termo.strip().lower()
        if not termo_clean:
            return "Informe um termo não vazio para busca no grafo."

        matched_triples = []
        for s, p, o in self.graph:
            s_str = str(s).lower()
            p_str = str(p).lower()
            o_str = str(o).lower()
            if termo_clean in s_str or termo_clean in p_str or termo_clean in o_str:
                matched_triples.append(
                    f"{self._format_node(s)}  --[{self._format_node(p)}]-->  {self._format_node(o)}"
                )
                if len(matched_triples) >= max(1, min(int(limite), 100)):
                    break

        if not matched_triples:
            return f"Nenhuma tripla encontrada contendo o termo '{termo}'."

        return (
            f"Triplas encontradas para '{termo}' ({len(matched_triples)} resultados):\n"
            + "\n".join(matched_triples)
        )

    def explorar_entidade(self, entidade: str) -> str:
        if self.load_error:
            return self.load_error

        alvo = entidade.strip()
        if not alvo:
            return "Informe o nome local, prefixo:nome ou URI da entidade."

        alvo_local = self._local_name(alvo.split(":")[-1] if ":" in alvo and not alvo.startswith("http") else alvo).lower()

        outgoing = []
        incoming = []

        for s, p, o in self.graph:
            s_norm = self._format_node(s)
            o_norm = self._format_node(o)
            s_local = self._local_name(str(s)).lower()
            o_local = self._local_name(str(o)).lower()

            if (
                str(s).lower() == alvo.lower()
                or s_norm.lower() == alvo.lower()
                or s_local == alvo_local
            ):
                outgoing.append(f"{s_norm}  --[{self._format_node(p)}]-->  {o_norm}")

            if (
                str(o).lower() == alvo.lower()
                or o_norm.lower() == alvo.lower()
                or o_local == alvo_local
            ):
                incoming.append(f"{s_norm}  --[{self._format_node(p)}]-->  {o_norm}")

        if not outgoing and not incoming:
            return (
                f"Nenhuma tripla encontrada diretamente para a entidade '{entidade}'. "
                "Tente usar 'buscar_termo_no_grafo' ou 'obter_esquema_ontologia'."
            )

        lines = [f"=== Exploração da Entidade: {entidade} ==="]
        if outgoing:
            lines.append(f"\n--- Relações de Saída / Propriedades da Entidade ({len(outgoing)}) ---")
            lines.extend(outgoing[:80])
        if incoming:
            lines.append(f"\n--- Relações de Entrada / Onde a Entidade é Referenciada ({len(incoming)}) ---")
            lines.extend(incoming[:80])

        return "\n".join(lines)


ONTOLOGY_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "obter_esquema_ontologia",
            "description": (
                "Retorna um resumo completo do esquema da ontologia do Capstone do Insper: "
                "prefixos/namespaces, classes (owl:Class), object properties, datatype properties "
                "e lista de indivíduos/instâncias."
            ),
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
            "name": "executar_consulta_sparql",
            "description": (
                "Executa uma consulta SPARQL (SELECT, ASK, DESCRIBE, CONSTRUCT) sobre o grafo "
                "da ontologia Turtle do Capstone. Os prefixos registrados na ontologia são "
                "incluídos automaticamente."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Consulta SPARQL completa a ser executada no grafo RDF.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_termo_no_grafo",
            "description": (
                "Busca uma palavra-chave ou substring (case-insensitive) em todos os sujeitos, "
                "predicados, objetos, rótulos (rdfs:label) e comentários (rdfs:comment) do grafo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "termo": {
                        "type": "string",
                        "description": "Termo ou palavra-chave para buscar nas triplas da ontologia.",
                    },
                    "limite": {
                        "type": "integer",
                        "description": "Número máximo de triplas retornadas (padrão: 40).",
                        "default": 40,
                    },
                },
                "required": ["termo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explorar_entidade",
            "description": (
                "Retorna todas as triplas de saída (propriedades da entidade) e de entrada "
                "(onde ela é referenciada) para uma classe, propriedade ou indivíduo específico."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entidade": {
                        "type": "string",
                        "description": "Nome local (ex.: 'Projeto'), QName (ex.: ':Projeto') ou URI completa da entidade.",
                    }
                },
                "required": ["entidade"],
            },
        },
    },
]


def execute_ontology_tool(ontology_tool: OntologyGraphTool, name: str, arguments_json: str) -> str:
    try:
        args = json.loads(arguments_json) if arguments_json else {}
    except json.JSONDecodeError:
        args = {}

    if name == "obter_esquema_ontologia":
        return ontology_tool.obter_esquema_ontologia()
    if name == "executar_consulta_sparql":
        return ontology_tool.executar_consulta_sparql(query=str(args.get("query", "")))
    if name == "buscar_termo_no_grafo":
        return ontology_tool.buscar_termo_no_grafo(
            termo=str(args.get("termo", "")),
            limite=int(args.get("limite", 40)),
        )
    if name == "explorar_entidade":
        return ontology_tool.explorar_entidade(entidade=str(args.get("entidade", "")))
    return f"Ferramenta desconhecida: {name}"

