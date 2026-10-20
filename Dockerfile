# PriceVow - one container, ready for Fly.io / Render / Railway.
# Build:  docker build -t pricevow .
# Run:    docker run -p 8000:8000 pricevow
FROM python:3.12-slim

# ffmpeg powers the walkthrough-video frame sampling.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/pricevow
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data/golden_set_template.csv ./data/golden_set_template.csv
COPY scripts ./scripts

# The SQLite file lives in /srv/pricevow/data - mount a volume there in
# production so the calibration dataset (the moat) survives restarts.
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
