Install it with either local or cloud mode, right now what I'm using is gemini flash for worker role and llama 3.3 70B for supervisor for cloud mode, you can change to local mode by setting RUN_MODE = local in the .env (set it to cloud otherwise), the local model I am using is qwen 3 for worker and llama 3.1 for supervisor. 
Run with
docker compose up --build
And query with 
docker compose run auditor-agent python src/main.py "your intput"
First run might take a while to initialize knowledge base, afterward it will be faster
Can be improve by using a better supervisor but I don't have enough vram to test it out
