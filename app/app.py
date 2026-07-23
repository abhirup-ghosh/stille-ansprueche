"""Phase 5b: Streamlit chat UI over the RAG flow, with Postgres conversation/feedback logging."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from langdetect import detect

from src import db
from src.eval_rag import judge_relevance
from src.llm import LLMClient
from src.rag import PROMPT_VARIANTS, answer

DISCLAIMER = (
    "Dies ist ein Informationsassistent und keine Rechtsberatung. Verbindliche Auskünfte gibt "
    "nur die zuständige Behörde. Datengrundlage: ifo-Institut Sozialleistungsinventur & "
    "offizielle Portale."
)

st.set_page_config(page_title="Stille Ansprüche", page_icon="🧾")


@st.cache_resource
def _init_db_once() -> None:
    db.init_db()


@st.cache_resource
def _get_llm_client() -> LLMClient:
    return LLMClient()


_init_db_once()

st.title("Stille Ansprüche")
st.caption("Entdecke Sozialleistungen, die dir zustehen könnten — grounded in official sources.")
st.info(DISCLAIMER)

with st.sidebar:
    st.header("Einstellungen")
    prompt_variant = st.selectbox("Prompt variant", ["v_best"] + list(PROMPT_VARIANTS.keys()), index=0)
    k = st.number_input("k (retrieved documents)", min_value=1, max_value=20, value=5)
    show_context = st.checkbox("Retrieved context anzeigen (debug)", value=False)

if "history" not in st.session_state:
    st.session_state.history = []

for entry in st.session_state.history:
    with st.chat_message("user"):
        st.markdown(entry["question"])
    with st.chat_message("assistant"):
        st.markdown(entry["answer"])
        with st.expander("Quellen"):
            for source in entry["sources"]:
                link = source["official_url"] or "siehe zuständige Behörde"
                st.markdown(f"- **{source['name']}** — {source['legal_norm']} — {link}")
        if show_context:
            with st.expander("Retrieved context (debug)"):
                st.json(entry["sources"])

        if entry["feedback_value"] is None:
            col_up, col_down, _ = st.columns([1, 1, 6])
            if col_up.button("👍", key=f"up_{entry['conversation_id']}"):
                db.insert_feedback(entry["conversation_id"], 1)
                entry["feedback_value"] = 1
                st.toast("Danke!")
                st.rerun()
            if col_down.button("👎", key=f"down_{entry['conversation_id']}"):
                db.insert_feedback(entry["conversation_id"], -1)
                entry["feedback_value"] = -1
                st.toast("Danke!")
                st.rerun()
        else:
            st.caption("Danke für dein Feedback!" if entry["feedback_value"] == 1 else "Danke für dein Feedback.")

question = st.chat_input("Beschreibe deine Lebenslage...")
if question:
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Antwort wird erstellt..."):
            rag_answer = answer(question, prompt_variant=prompt_variant, k=k)
        st.markdown(rag_answer.answer)

        with st.expander("Quellen"):
            for source in rag_answer.sources:
                link = source["official_url"] or "siehe zuständige Behörde"
                st.markdown(f"- **{source['name']}** — {source['legal_norm']} — {link}")
        if show_context:
            with st.expander("Retrieved context (debug)"):
                st.json(rag_answer.sources)

    try:
        lang = detect(question)
    except Exception:  # noqa: BLE001 — langdetect raises on very short/ambiguous input
        lang = "de"

    retrieved_ids = [source["id"] for source in rag_answer.sources]
    conversation_id = db.insert_conversation(question, lang, retrieved_ids, rag_answer)

    try:
        relevance, _usage = judge_relevance(_get_llm_client(), question, rag_answer.answer)
        db.update_conversation_relevance(conversation_id, relevance.label, relevance.explanation)
    except Exception:  # noqa: BLE001 — judging must never break the app
        pass

    st.session_state.history.append({
        "conversation_id": conversation_id,
        "question": question,
        "answer": rag_answer.answer,
        "sources": rag_answer.sources,
        "feedback_value": None,
    })
    st.rerun()
