import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from kers_assistant import CatalogError, generate_sales_answer, retrieve


load_dotenv()

PROJECT_DIR = Path(__file__).resolve().parent
PROTOCOL_VERSION = 1
AGENT_NAME = "kers-deepchat-agent"
AGENT_VERSION = "1.0.0"


@dataclass
class SessionState:
    session_id: str
    cwd: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_prompt: str = ""


class AcpError(Exception):
    def __init__(self, code: int, message: str, data: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data or {}


class KersDeepChatAgent:
    def __init__(self) -> None:
        self.sessions: dict[str, SessionState] = {}

    def handle(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        method = payload.get("method")
        params = payload.get("params") or {}
        request_id = payload.get("id")

        if method == "initialize":
            result = {
                "protocolVersion": PROTOCOL_VERSION,
                "agentCapabilities": {
                    "loadSession": False,
                    "promptCapabilities": {"image": False, "audio": False, "embeddedContext": False},
                    "sessionCapabilities": {},
                },
                "agentInfo": {"name": AGENT_NAME, "version": AGENT_VERSION},
            }
            return self._success(request_id, result)

        if method == "session/new":
            cwd = params.get("cwd") or params.get("workdir") or str(PROJECT_DIR)
            session_id = f"kers-{uuid.uuid4().hex}"
            self.sessions[session_id] = SessionState(session_id=session_id, cwd=str(cwd))
            return self._success(request_id, {"sessionId": session_id})

        if method == "session/load":
            raise AcpError(-32601, "session/load nao suportado por este agente.")

        if method in {"session/set_mode", "session/setMode"}:
            return self._success(request_id, {"ok": True})

        if method in {"session/set_model", "session/setModel"}:
            return self._success(request_id, {"ok": True})

        if method == "session/cancel":
            session_id = params.get("sessionId")
            if request_id is None:
                return None
            if session_id and session_id in self.sessions:
                return self._success(request_id, {"stopReason": "cancelled"})
            raise AcpError(-32602, "sessionId invalido para cancelamento.")

        if method == "session/prompt":
            session_id = params.get("sessionId")
            if not session_id or session_id not in self.sessions:
                raise AcpError(-32602, "sessionId invalido para envio de prompt.")

            prompt_text = self._extract_prompt_text(params)
            if not prompt_text:
                raise AcpError(-32602, "Nenhum texto foi enviado no prompt.")

            session = self.sessions[session_id]
            session.last_prompt = prompt_text

            try:
                rows = retrieve(prompt_text, top_k=6, min_score=1)
                answer = generate_sales_answer(prompt_text, rows, response_style="deepchat")
            except CatalogError as exc:
                answer = f"Nao consegui acessar a base KERS agora. Detalhe: {exc}"

            self._send_update(
                session_id,
                {
                    "sessionUpdate": "session_info_update",
                    "title": self._build_title(prompt_text, answer),
                    "updatedAt": datetime.now(timezone.utc).isoformat(),
                },
            )

            for chunk in self._split_chunks(answer):
                self._send_update(
                    session_id,
                    {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": chunk},
                    },
                )

            return self._success(request_id, {"stopReason": "end_turn"})

        raise AcpError(-32601, f"Metodo nao suportado: {method}")

    def _extract_prompt_text(self, params: dict[str, Any]) -> str:
        blocks = params.get("content") or params.get("prompt") or []
        parts: list[str] = []
        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text = str(block.get("text", "")).strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()

    def _build_title(self, prompt_text: str, answer: str) -> str:
        first_line = answer.splitlines()[0].strip() if answer.strip() else ""
        if "Produto recomendado:" in first_line:
            return first_line.replace("Produto recomendado:", "").strip()[:80] or "KERS"
        return prompt_text.strip()[:80] or "KERS"

    def _split_chunks(self, answer: str) -> list[str]:
        paragraphs = [paragraph.strip() for paragraph in answer.split("\n\n") if paragraph.strip()]
        if not paragraphs:
            return ["Sem resposta disponivel."]
        return [f"{paragraph}\n\n" for paragraph in paragraphs[:-1]] + [paragraphs[-1]]

    def _send_update(self, session_id: str, update: dict[str, Any]) -> None:
        message = {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {"sessionId": session_id, "update": update},
        }
        self._write_message(message)

    def _success(self, request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _error(self, request_id: Any, error: AcpError) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": error.code, "message": error.message},
        }
        if error.data:
            payload["error"]["data"] = error.data
        return payload

    def _write_message(self, payload: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(payload, ensure_ascii=True) + "\n")
        sys.stdout.flush()


def main() -> int:
    agent = KersDeepChatAgent()

    while True:
        raw_line = sys.stdin.readline()
        if raw_line == "":
            return 0

        raw_line = raw_line.strip()
        if not raw_line:
            continue

        try:
            payload = json.loads(raw_line)
            response = agent.handle(payload)
            if response is not None:
                agent._write_message(response)
        except AcpError as exc:
            request_id = None
            try:
                request_id = payload.get("id")  # type: ignore[name-defined]
            except Exception:
                request_id = None
            agent._write_message(agent._error(request_id, exc))
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            request_id = None
            try:
                request_id = payload.get("id")  # type: ignore[name-defined]
            except Exception:
                request_id = None
            internal_error = AcpError(
                -32603,
                "Erro interno no agente KERS.",
                data={"details": str(exc), "cwd": os.getcwd()},
            )
            agent._write_message(agent._error(request_id, internal_error))


if __name__ == "__main__":
    raise SystemExit(main())
