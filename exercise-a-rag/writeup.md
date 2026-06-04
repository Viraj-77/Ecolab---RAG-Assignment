# Ecolab RAG Agent Write-Up

## Key Design Decisions

### Chunking Strategy
We implemented a token-based chunking strategy using the `tiktoken` library with the `cl100k_base` encoding (the same tokenizer used by modern OpenAI models). 
* **Chunk Size:** Set to `800` tokens, which provides enough context (roughly 600 words) for the LLM to understand complete concepts without diluting the semantic meaning.
* **Overlap:** Set to `100` tokens (12.5%). This overlap ensures that concepts split across chunk boundaries are not lost, preventing abrupt cut-offs mid-sentence or mid-paragraph.

### Retrieval (Top-K)
We set our retrieval `TOP_K` to `4`. When a user asks a question, the vector database returns the 4 most semantically relevant chunks. This number was chosen as a trade-off: it provides sufficient background context from multiple sources without overwhelming the model's context window or introducing too much noise.

### Prompt Structure and Tool Routing
The `SYSTEM_PROMPT` explicitly defines the agent's persona ("Ecolab assistant") and provides clear instructions on when to use each capability:
* Use the **knowledge base** for conceptual questions, regulations, and best practices.
* Use the **USGS tool (`get_water_quality`)** for live readings and current numerical data.
We use OpenAI's native `tool_choice="auto"`, allowing the model to make autonomous routing decisions based strictly on the system prompt guidelines and the user's input.

## How RAG and Tool Calling are Combined (Control Flow)
The agent integrates RAG and tool-calling seamlessly through a native `while True` loop, entirely avoiding heavy orchestration frameworks. The control flow is as follows:
1. **Initial Augmentation (RAG):** When the user submits a message, we first embed the query and retrieve `TOP_K` chunks from ChromaDB.
2. **Context Injection:** The retrieved chunks are appended to the user's message as "Context from documents", and this augmented message is added to the conversation memory.
3. **Agent Loop:** The conversation (including the system prompt, history, and the new augmented message) is sent to the Azure OpenAI model along with the available tool schemas.
4. **Execution or Completion:**
   * **If the model decides to call a tool:** We parse the tool call, execute the corresponding Python function (e.g., querying the USGS API), append the raw tool result to the memory as a `tool` role message, and `continue` the loop to call the model again.
   * **If the model does not call a tool:** It has decided it has enough information (either from the RAG context or from a previous tool execution). It generates the final response, which is returned to the user, breaking the loop.

## Trade-offs Made
* **Azure OpenAI vs. Sentence Transformers:** We chose to use Azure OpenAI for generating embeddings rather than local `sentence-transformers`. The primary reason for this decision was a security issue  that prevented us from securely downloading and loading the local transformer models. As a secondary benefit, using Azure OpenAI offloads the memory and compute requirements of embedding generation to the cloud API, allowing our local application to run with a lighter memory footprint.
* **USGS API vs. Alternatives:** We chose the USGS Water Quality Portal API over other options (like OpenAQ or EPA FRS) because our indexed document corpus is specifically focused on water treatment and hygiene. While the USGS API does not provide every possible environmental metric, it suited our documents perfectly and was by far the most relevant API to pair with our knowledge base.

## Known Limitations & Next Steps
* **Persistence:** Currently, the conversation history only persists for the duration of the Streamlit session. A logical next step is to integrate a persistent database (like PostgreSQL or Redis) to save chat histories across sessions.
* **Scalability:** The local ChromaDB setup would need to be migrated to a hosted solution (like Pinecone or Qdrant Cloud) if we were to ingest thousands of documents or serve many concurrent users.
* **Prompt Injection / Guardrails:** The current implementation blindly trusts the retrieved documents. In a production environment, we would need to implement guardrails to prevent prompt injection attacks originating from compromised or malicious documents in the corpus.
* **Evaluation:** We currently lack an automated evaluation pipeline (like RAGAS) to formally score the accuracy and relevancy of the retrieved chunks.

## Example Outputs

### 1. RAG-Only Query
<!-- Replace the path below with your RAG-only screenshot -->
![RAG-Only Query](./images/rag_only_query.png)

### 2. Tool-Only Query
<!-- Replace the path below with the Tool-only screenshot you just uploaded -->
![Tool-Only Query](./images/tool_only_query.png)

### 3. Combined Query
<!-- Replace the path below with your Combined query screenshot -->
![Combined Query](./images/combined_query.png)
