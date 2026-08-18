import streamlit as st
import requests
import uuid

API_URL = "http://127.0.0.1:8000"
API_KEY = "dev-key-123"
HEADERS = {"x-api-key": API_KEY}

st.set_page_config(page_title="NL SQL Engine", layout="wide")
st.title("Natural Language Database Query Engine")
st.caption("Ask questions about the Northwind database in plain English")

# session initialisation 
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

#sidebar
with st.sidebar:
    st.header("Session")
    st.caption(f"Session ID: {st.session_state.session_id[:8]}...")
    if st.button("New conversation"):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()



# session id per browser session
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

# display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if "sql" in msg:
            with st.expander("Generated SQL"):
                st.code(msg["sql"], language="sql")
        if "rows" in msg and msg["rows"]:
            with st.expander("Results"):
                st.dataframe(msg["rows"])
        if "confidence" in msg:
            st.caption(f"Confidence: {msg['confidence']} · Intent: {msg['intent']}")
            if msg.get("warning"):
                st.warning(msg["warning"])

# input
if prompt := st.chat_input("Ask a question about the data..."):
    # show user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    # call API
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                response = requests.post(
                    f"{API_URL}/query",
                    headers=HEADERS,
                    json={"query": prompt, "session_id": st.session_state.session_id}
                )
                data = response.json()

                if data.get("error"):
                    st.error(f"Error: {data['error']}")
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"Error: {data['error']}"
                    })
                else:
                    # show results
                    st.write("Query executed successfully.")
                    with st.expander("Generated SQL", expanded=True):
                        st.code(data["sql"], language="sql")
                    if data["rows"]:
                        with st.expander("Results", expanded=True):
                            st.dataframe(data["rows"])
                    else:
                        st.info("Query returned no results.")

                    st.caption(f"Confidence: {data['confidence']} · Intent: {data['intent']} · Cached: {data['cached']}")
                    if data.get("warning"):
                        st.warning(data["warning"])

                    # get explanation
                    explain_resp = requests.post(
                        f"{API_URL}/explain",
                        headers=HEADERS,
                        json={"sql": data["sql"]}
                    )
                    explanation = explain_resp.json().get("explanation", "")
                    if explanation:
                        st.info(f"💡 {explanation}")

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": "Query executed successfully.",
                        "sql": data["sql"],
                        "rows": data["rows"],
                        "confidence": data["confidence"],
                        "intent": data["intent"],
                        "warning": data.get("warning")
                    })

            except Exception as e:
                st.error(f"Could not connect to API: {e}")