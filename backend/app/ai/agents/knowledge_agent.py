"""
Knowledge Agent
---------------
Thin LangGraph wrapper around the existing `knowledge_tool` (hybrid
BM25 + Pinecone RAG service). Retrieval internals live in
`ai/services/rag_service.py` and are untouched.

Owns: retrieved_documents, retrieved_chunks, tool_outputs["knowledge"]
"""
from typing import Any, Dict

from ..graph.state import ConversationState
from ..tools.kpi_tools import knowledge_tool  # existing tool
from .base import node


@node("knowledge")
def knowledge_agent(state: ConversationState) -> Dict[str, Any]:
    tool_data = knowledge_tool(state.get("user_query", ""))

    tool_outputs = dict(state.get("tool_outputs") or {})
    tool_outputs["knowledge"] = tool_data

    sources = tool_data.get("sources", [])

    return {
        "tool_outputs": tool_outputs,
        "retrieved_documents": sources,
        "retrieved_chunks": [
            {"source": s.get("source"), "snippet": s.get("snippet"), "score": s.get("score")}
            for s in sources
        ],
    }
