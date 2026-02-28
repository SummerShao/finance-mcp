FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create cache directory
RUN mkdir -p /tmp/mcp_cache/tushare

# Default: SSE transport for Docker (HTTP accessible)
ENV MCP_TRANSPORT=sse
ENV MCP_PORT=8000

EXPOSE 8000

CMD ["python", "server.py"]
