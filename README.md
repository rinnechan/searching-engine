# Auditor Agent: Hybrid Searching Engine

An agentic search and auditing system built with a dual-model architecture. The system utilizes a **Supervisor** to manage logic and a **Worker** to handle information retrieval and processing. It supports seamless switching between high-performance **Cloud** models and privacy-focused **Local** models.

---

## System Architecture

The project implements a "Supervisor-Worker" pattern:
* **Supervisor:** High-reasoning model that plans the search strategy and audits the worker's output.
* **Worker:** Fast, efficient model that executes queries and parses data.

### Model Stack
| Environment | Supervisor | Worker |
| :--- | :--- | :--- |
| **Cloud** (Default) | Llama 3.3 70B | Gemini 2.5 Flash |
| **Local** | Llama 3.1 8B | Qwen 3 |

---

## Installation & Setup

### 1. Prerequisites
* [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
* (Optional) NVIDIA Container Toolkit for GPU acceleration in local mode.

### 2. Environment Configuration
Create a `.env` file in the root directory and configure your preferred mode:

```bash
# Choose 'cloud' or 'local'
RUN_MODE=cloud

# API Keys for Cloud Mode
GEMINI_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key
```

Build the environment and prepare the knowledge base:
```bash
docker compose up --build
```
Query for searching
```
docker compose run auditor-agent python src/main.py "Your search query here"\
```

Can be improve if you change local model to one with more parameters, but I have limited vram so cannot test it out
Currently working on deepeval to better evaluate

Post-Mortem & Performance Notes: 

*Accuracy/Faithfulness: The system achieved a core accuracy of 0.67. While the Auditor correctly identified HS Code 8518.30.10 in the evidence , the DeepEval verification layer flagged a false negative on the specific string matching of the 8-digit code.

Latency: Total latency reached 118.28s, exceeding the 60s target.

Root Cause: This was caused by the Recursive Search logic. Because the evaluator rejected the initial findings, the system performed three full attempts to self-correct.

Local Execution: This benchmark was run on local consumer hardware (RTX 30-series/40-series). Production-grade GPUs with higher VRAM (e.g., A100 or RTX 5090) would allow for larger models (14B+) and significantly faster token generation, likely reducing Attempt 0 latency to well under 60s.

Future improvements:

Evaluation Refinement: Adjust the DeepEval prompt to better recognize structured tariff codes to prevent unnecessary recursion loops.

Local Model Scaling: Transition to 14B or 30B models for the Supervisor in local mode to increase reasoning capabilities to ~80% accuracy.