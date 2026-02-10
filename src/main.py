import argparse
import logging
import traceback
import uuid
import sys
import time
from dotenv import load_dotenv
from src.graph.builder import graph
from src.ingestion.parse import get_or_create_index

def setup_logging():
    # Configure logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler = logging.FileHandler("audit.log", mode='w', delay=False)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    class StreamToLogger:
        def __init__(self, logger_level):
            self.logger_level = logger_level

        def write(self, buf):
            for line in buf.rstrip().splitlines():
                logging.log(self.logger_level, line.rstrip())

        def flush(self):
            pass

    sys.stdout = StreamToLogger(logging.INFO)
    sys.stderr = StreamToLogger(logging.ERROR)
    return logger

logger = setup_logging()

def main():
    load_dotenv()
    start_time = time.time()

    logger.info("Initializing knowledge base...")
    get_or_create_index()

    parser = argparse.ArgumentParser(description="Autonomous Regulatory Auditor")
    parser.add_argument("query", type=str, help="The product to classify")
    parser.add_argument("--thread", type=str, default=str(uuid.uuid4())[:8], help="Unique Audit ID")
    args = parser.parse_args()

    config = {"configurable": {"thread_id": f"audit_{args.thread}"}}
    
    initial_state = {
        "query": args.query,
        "worker_results": [],
        "step_count": 0
    }
    
    logger.info(f"--- STARTING AUDIT: {args.thread} ---")
    
    try:
        final_state = graph.invoke(initial_state, config=config)
        end_time = time.time()
        latency = end_time - start_time
        faith_score = final_state.get("faithfulness_score", 0.0)
        total_tokens = final_state.get("total_tokens", 0) 
        
        # Asumming using token cost from GROQ, can change based on your LLM pricing
        token_cost = (total_tokens / 1000) * 0.0006 

        print(f"""
BENCHMARK REPORT
------------------------------------
QUERY: {args.query}
HS-CODE: {final_state.get('final_hscode', 'N/A')}
CONFIDENCE: {final_state.get('final_confidence', 'N/A')}

PARETO FRONTIER:
- Accuracy (Faithfulness): {faith_score:.2f}
- Latency: {latency:.2f}s (Target: <60s)
- Token Cost: ${token_cost:.6f}
------------------------------------
""")
        
    except Exception as e:
        logger.error(f"Audit failed: {e}")
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    main()