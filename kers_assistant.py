import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import pandas as pd

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - depends on local environment
    OpenAI = None


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_CSV_PATH = "kers_base_profissional_publica.csv"
DEFAULT_MODEL_NAME = "gpt-5.4"
SEARCH_COLUMNS = [
    "nome",
    "categoria",
    "subcategoria",
    "descricao_tecnica",
    "aplicacao",
    "publico_indicado",
    "diferencial",
    "argumento_venda",
    "objecao_comum",
    "resposta_objecao",
    "venda_casada",
]
REQUIRED_COLUMNS = [
    "sku",
    "nome",
    "categoria",
    "subcategoria",
    "codigo",
    "descricao_tecnica",
    "aplicacao",
    "publico_indicado",
    "diferencial",
    "risco_ou_cuidado",
    "argumento_venda",
    "objecao_comum",
    "resposta_objecao",
    "venda_casada",
    "source_url",
    "status_dados",
]
INSUFFICIENT_CONTEXT_MESSAGE = (
    "O contexto publico disponivel nao trouxe informacoes suficientes para responder "
    "com seguranca. Vale consultar a base interna da KERS ou enriquecer o catalogo."
)


class KersAssistantError(Exception):
    """Base error for catalog and model issues."""


class CatalogError(KersAssistantError):
    """Raised when the CSV cannot be loaded or validated."""


class LLMConfigurationError(KersAssistantError):
    """Raised when the OpenAI client cannot be configured."""


class LLMResponseError(KersAssistantError):
    """Raised when the OpenAI API call fails or returns no text."""


def _resolve_csv_path(csv_path: str | None = None) -> Path:
    raw_path = csv_path or os.getenv("KERS_CSV_PATH", DEFAULT_CSV_PATH)
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_DIR / path
    return path


@lru_cache(maxsize=4)
def _load_catalog_cached(resolved_path: str) -> pd.DataFrame:
    csv_file = Path(resolved_path)
    if not csv_file.exists():
        raise CatalogError(f"CSV nao encontrado em: {csv_file}")

    try:
        catalog = pd.read_csv(csv_file, dtype=str).fillna("")
    except Exception as exc:  # pragma: no cover - depends on local file contents
        raise CatalogError(f"Nao foi possivel ler o CSV: {csv_file}") from exc

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in catalog.columns]
    if missing_columns:
        missing_list = ", ".join(missing_columns)
        raise CatalogError(f"CSV invalido. Colunas ausentes: {missing_list}")

    return catalog


def load_catalog(csv_path: str | None = None) -> pd.DataFrame:
    return _load_catalog_cached(str(_resolve_csv_path(csv_path)))


def normalize(text: str) -> list[str]:
    cleaned = unicodedata.normalize("NFKD", str(text).lower())
    cleaned = cleaned.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^0-9a-z\s]", " ", cleaned)
    return [token for token in cleaned.split() if len(token) > 1]


def score_row(question_tokens: set[str], row: pd.Series) -> int:
    searchable_text = " ".join(str(row.get(column, "")) for column in SEARCH_COLUMNS)
    row_tokens = set(normalize(searchable_text))
    return len(question_tokens & row_tokens)


def _empty_result_frame(base: pd.DataFrame) -> pd.DataFrame:
    columns = list(base.columns)
    if "score" not in columns:
        columns.append("score")
    return pd.DataFrame(columns=columns)


def retrieve(question: str, top_k: int = 8, min_score: int = 1, csv_path: str | None = None) -> pd.DataFrame:
    base = load_catalog(csv_path)
    question_tokens = set(normalize(question))

    if not question_tokens:
        return _empty_result_frame(base)

    scored = base.copy()
    scored["score"] = scored.apply(lambda row: score_row(question_tokens, row), axis=1)
    scored = scored[scored["score"] >= min_score]

    if scored.empty:
        return _empty_result_frame(base)

    scored = scored.sort_values(["score", "sku", "nome"], ascending=[False, True, True])
    return scored.head(top_k).reset_index(drop=True)


def build_context(rows: pd.DataFrame, extra_fields: Iterable[str] | None = None) -> str:
    if rows.empty:
        return ""

    fields = [
        ("SKU", "sku"),
        ("Produto", "nome"),
        ("Categoria", None),
        ("Codigo", "codigo"),
        ("Descricao tecnica", "descricao_tecnica"),
        ("Aplicacao", "aplicacao"),
        ("Publico indicado", "publico_indicado"),
        ("Diferencial", "diferencial"),
        ("Risco ou cuidado", "risco_ou_cuidado"),
        ("Argumento de venda", "argumento_venda"),
        ("Objecao comum", "objecao_comum"),
        ("Resposta a objecao", "resposta_objecao"),
        ("Venda casada", "venda_casada"),
        ("Status dos dados", "status_dados"),
        ("Fonte", "source_url"),
    ]

    if extra_fields:
        for field_name in extra_fields:
            fields.append((field_name, field_name))

    blocks: list[str] = []
    for _, row in rows.iterrows():
        lines: list[str] = []
        for label, column in fields:
            if label == "Categoria":
                value = f'{row.get("categoria", "")} / {row.get("subcategoria", "")}'.strip(" /")
            else:
                value = row.get(column or "", "")

            if value:
                lines.append(f"{label}: {value}")

        blocks.append("\n".join(lines))

    return "\n\n---\n\n".join(blocks)


def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or api_key == "your_api_key_here":
        raise LLMConfigurationError(
            "Defina OPENAI_API_KEY no arquivo .env antes de consultar o modelo."
        )

    if OpenAI is None:
        raise LLMConfigurationError(
            "A biblioteca openai nao esta instalada. Rode `pip install -r requirements.txt`."
        )

    return OpenAI(api_key=api_key)


def ask_llm(question: str, context: str, system_prompt: str, model_name: str | None = None) -> str:
    if not context.strip():
        return INSUFFICIENT_CONTEXT_MESSAGE

    client = get_openai_client()
    model = model_name or os.getenv("OPENAI_MODEL", DEFAULT_MODEL_NAME)

    try:
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Contexto:\n{context}\n\nPergunta do vendedor: {question}",
                },
            ],
        )
    except Exception as exc:  # pragma: no cover - depends on network/API availability
        raise LLMResponseError(f"Falha ao consultar a OpenAI: {exc}") from exc

    answer = getattr(response, "output_text", "").strip()
    if not answer:
        raise LLMResponseError("A OpenAI retornou uma resposta vazia.")

    return answer
