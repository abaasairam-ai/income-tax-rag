"""MCP server exposing the Income Tax RAG as a tool Claude can call.

    Claude Desktop launches this. Do not run it by hand expecting output --
    it speaks MCP over stdin/stdout and will just sit there silently.

WHAT THIS IS
  ask.py is a complete RAG: retrieve chunks, then have a local model write the
  answer. This server keeps the first half and throws away the second, because
  under MCP *Claude is the model*. So we hand Claude the source text and the
  citations, and Claude writes the answer.

WHY THAT IS BETTER, NOT JUST DIFFERENT
  This server never generates a sentence, so it cannot hallucinate. It can only
  retrieve the wrong chunk -- and that is a retrieval problem, which is
  measurable. Two failure modes collapse into one, and the survivor is the one
  the eval set can actually test.

NOTHING MAY PRINT
  A stray print() corrupts the protocol. Everything diagnostic goes to stderr,
  which Claude Desktop captures in its logs.
"""
import os
import sys

# ask.py lives next to this file. Import its functions rather than copying them
# -- expand() and the MAX_DISTANCE guardrail are the real IP here, and two
# copies would drift apart the first time either is tuned.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ask import expand, retrieve, cite, MAX_DISTANCE, DB_DIR, COLLECTION  # noqa: E402
from embedder import mode_name  # noqa: E402

# MCP SDK 2.x. In 1.x this class was `mcp.server.fastmcp.FastMCP`; 2.0 renamed
# it to MCPServer and moved it up a level. Same decorator API, so only the
# import and the constructor changed. If a tutorial says FastMCP, it is 1.x.
from mcp.server import MCPServer  # noqa: E402

mcp = MCPServer(name="income-tax-rag")


@mcp.tool()
def search_income_tax_act(question: str, k: int = 5, unit: str = "") -> str:
    """Search the Income-tax Act 2025 and Income-tax Rules 2026 and return the
    exact provisions with section citations.

    Use this for any question about Indian income-tax law: computation of
    income, deductions, exemptions, residency, filing and registration
    procedure, or what a specific section or rule says.

    Returns source text only. It does NOT interpret and does NOT give advice --
    read the returned provisions and answer from them, citing the section.

    Two things this corpus does NOT contain, so do not infer them:
      - RATES (slab, surcharge, cess, TDS rates) live in the Finance Act, which
        is not indexed. Say so rather than guessing a number.
      - 1961-Act section numbers (80C, 194J). The 1961-to-2025 mapping is not
        indexed. Ask the user for the 2025 section.

    Args:
        question: the tax question, in plain English.
        k: how many provisions to return. 5 is usually right; raise to 8-10 for
           broad questions, lower to 3 when you want only the closest match.
        unit: "section" to search only the Act, "rule" to search only the Rules.
              Leave empty to search both. (These are the literal values in the
              chunk metadata -- "act" matches nothing and silently returns zero
              results.)
    """
    hits = retrieve(question, k=k, unit=(unit or None))

    if not hits:
        return "No provisions found. The index may be empty -- check the server log."

    # THE GUARDRAIL, ported deliberately.
    #
    # ask.py refuses to call the model when the closest chunk is further than
    # MAX_DISTANCE, because of a real failure: asked "what is TDS", retrieval
    # returned noise at distance 1.46 and the model invented a citation to a
    # section that does not say what it claimed.
    #
    # Claude is a stronger model than llama3.2, but the reasoning is unchanged:
    # if the retrieved text is not about the question, handing it over invites a
    # confident wrong answer. A refusal in code is not a refusal a model can
    # talk itself out of.
    best = min(h['distance'] for h in hits)
    if best > MAX_DISTANCE:
        return (
            f"NO RELIABLE MATCH. The closest indexed provision scored "
            f"{best:.3f}, beyond the relevance limit of {MAX_DISTANCE}.\n\n"
            "Tell the user this question is not covered by the indexed "
            "documents (Income-tax Act 2025 and Rules 2026). Do NOT answer it "
            "from general knowledge -- an unsourced answer is exactly what this "
            "limit exists to prevent."
        )

    blocks = [
        f"[{i}] {cite(h['meta'])}  (distance {h['distance']:.3f})\n{h['text']}"
        for i, h in enumerate(hits, 1)
    ]
    return (
        f"{len(hits)} provisions retrieved for: {question!r}\n"
        f"(query expanded to: {expand(question)!r})\n\n"
        + "\n\n".join(blocks)
        + "\n\n---\nAnswer from the text above only. State what the law says "
          "first, then cite the section. If it does not answer the question, "
          "say so."
    )


if __name__ == "__main__":
    # stderr only -- stdout belongs to the protocol.
    print(f"income-tax-rag MCP server", file=sys.stderr)
    print(f"  db         : {DB_DIR}", file=sys.stderr)
    print(f"  collection : {COLLECTION}", file=sys.stderr)
    print(f"  embedder   : {mode_name()}", file=sys.stderr)
    print(f"  max distance: {MAX_DISTANCE}", file=sys.stderr)
    mcp.run()
