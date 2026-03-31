import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_CSV_PATH = "kers_base_profissional_publica.csv"
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
    """Base error for catalog and response issues."""


class CatalogError(KersAssistantError):
    """Raised when the CSV cannot be loaded or validated."""


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


def _clean_value(row: pd.Series, field: str) -> str:
    return str(row.get(field, "")).strip()


def _ensure_sentence(text: str) -> str:
    cleaned = str(text).strip()
    if not cleaned:
        return ""
    if cleaned.endswith((".", "!", "?", ":")):
        return cleaned
    return f"{cleaned}."


def _category_label(row: pd.Series) -> str:
    category = _clean_value(row, "categoria")
    subcategory = _clean_value(row, "subcategoria")
    return " / ".join(value for value in [category, subcategory] if value)


def _product_heading(row: pd.Series) -> str:
    name = _clean_value(row, "nome") or "Produto sem nome"
    pieces = [name]

    sku = _clean_value(row, "sku")
    if sku:
        pieces.append(f"SKU {sku}")

    code = _clean_value(row, "codigo")
    if code:
        pieces.append(f"codigo {code}")

    category = _category_label(row)
    if category:
        pieces.append(category)

    return " | ".join(pieces)


def _build_section(title: str, parts: Iterable[str]) -> str:
    cleaned_parts = [part.strip() for part in parts if str(part).strip()]
    if not cleaned_parts:
        return ""
    body = " ".join(cleaned_parts)
    return f"{title}:\n{body}"


def _build_alternatives(rows: pd.DataFrame, limit: int = 2) -> str:
    if len(rows.index) <= 1:
        return ""

    lines: list[str] = []
    for _, row in rows.iloc[1 : 1 + limit].iterrows():
        name = _clean_value(row, "nome")
        sku = _clean_value(row, "sku")
        reason = (
            _clean_value(row, "aplicacao")
            or _clean_value(row, "diferencial")
            or _clean_value(row, "descricao_tecnica")
        )
        reason_text = _ensure_sentence(reason)
        label = name if not sku else f"{name} ({sku})"
        if reason_text:
            lines.append(f"- {label}: {reason_text}")
        else:
            lines.append(f"- {label}")

    if not lines:
        return ""

    return "Outras opcoes proximas:\n" + "\n".join(lines)


def _build_full_response(rows: pd.DataFrame) -> str:
    primary = rows.iloc[0]
    source_url = _clean_value(primary, "source_url")

    sections = [
        _build_section("Produto recomendado", [_product_heading(primary)]),
        _build_section(
            "Justificativa tecnica",
            [
                _ensure_sentence(_clean_value(primary, "descricao_tecnica")),
                _ensure_sentence(
                    f"Aplicacao principal: {_clean_value(primary, 'aplicacao')}"
                    if _clean_value(primary, "aplicacao")
                    else ""
                ),
                _ensure_sentence(
                    f"Publico indicado: {_clean_value(primary, 'publico_indicado')}"
                    if _clean_value(primary, "publico_indicado")
                    else ""
                ),
                _ensure_sentence(
                    f"Diferencial: {_clean_value(primary, 'diferencial')}"
                    if _clean_value(primary, "diferencial")
                    else ""
                ),
            ],
        ),
        _build_section("Como vender", [_ensure_sentence(_clean_value(primary, "argumento_venda"))]),
        _build_section("Objecao comum", [_ensure_sentence(_clean_value(primary, "objecao_comum"))]),
        _build_section(
            "Resposta a objecao",
            [_ensure_sentence(_clean_value(primary, "resposta_objecao"))],
        ),
        _build_section("Venda adicional", [_ensure_sentence(_clean_value(primary, "venda_casada"))]),
        _build_section("Cuidados", [_ensure_sentence(_clean_value(primary, "risco_ou_cuidado"))]),
        _build_alternatives(rows),
        _build_section("Fonte", [source_url]),
    ]
    return "\n\n".join(section for section in sections if section)


def _build_whatsapp_response(rows: pd.DataFrame) -> str:
    primary = rows.iloc[0]
    name = _clean_value(primary, "nome")
    sku = _clean_value(primary, "sku")
    heading = name if not sku else f"{name} ({sku})"
    snippets = [
        f"Produto recomendado: {heading}",
        _ensure_sentence(_clean_value(primary, "aplicacao")),
        _ensure_sentence(_clean_value(primary, "argumento_venda")),
        _ensure_sentence(
            f"Objecao: {_clean_value(primary, 'objecao_comum')}"
            if _clean_value(primary, "objecao_comum")
            else ""
        ),
        _ensure_sentence(
            f"Resposta: {_clean_value(primary, 'resposta_objecao')}"
            if _clean_value(primary, "resposta_objecao")
            else ""
        ),
        _ensure_sentence(
            f"Venda adicional: {_clean_value(primary, 'venda_casada')}"
            if _clean_value(primary, "venda_casada")
            else ""
        ),
    ]
    return "\n".join(part for part in snippets if part).strip()


def _build_deepchat_response(question: str, rows: pd.DataFrame) -> str:
    primary = rows.iloc[0]
    intro = _ensure_sentence(
        f"Pergunta recebida: {question}" if question.strip() else "Pergunta recebida."
    )
    body = _build_full_response(rows)
    category = _category_label(primary)
    notes = []
    if category:
        notes.append(f"Categoria principal: {category}.")
    status = _clean_value(primary, "status_dados")
    if status:
        notes.append(f"Status da base: {status}.")

    sections = [
        intro,
        body,
        "Notas de operacao:\n" + " ".join(notes) if notes else "",
    ]
    return "\n\n".join(section for section in sections if section)


def generate_sales_answer(question: str, rows: pd.DataFrame, response_style: str = "full") -> str:
    if rows.empty:
        return INSUFFICIENT_CONTEXT_MESSAGE

    if response_style == "whatsapp":
        return _build_whatsapp_response(rows)

    if response_style == "deepchat":
        return _build_deepchat_response(question, rows)

    return _build_full_response(rows)


def answer_question(
    question: str,
    top_k: int = 8,
    min_score: int = 1,
    response_style: str = "full",
    csv_path: str | None = None,
) -> tuple[str, pd.DataFrame]:
    rows = retrieve(question, top_k=top_k, min_score=min_score, csv_path=csv_path)
    return generate_sales_answer(question, rows, response_style=response_style), rows


def build_deepchat_prompt(question: str, rows: pd.DataFrame) -> str:
    context = build_context(rows)
    if not context:
        return INSUFFICIENT_CONTEXT_MESSAGE

    return (
        "Voce e o assistente comercial da KERS.\n"
        "Use somente o contexto abaixo e responda em portugues do Brasil.\n\n"
        f"Pergunta:\n{question}\n\n"
        f"Contexto:\n{context}"
    )
